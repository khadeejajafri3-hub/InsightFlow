"""
generator.py — VideoReportGenerator  (v2 — narration + music + CSV insights)
=============================================================================
New in v2
---------
  • Narration  : gTTS per-section, auto-synced to clip duration
  • Music      : MP3/WAV background, volume-controlled + fade-out
  • CSV mode   : pass csv_path to generate_report() for auto-insights

Dependencies
------------
    pip install moviepy pillow matplotlib numpy pandas
    pip install gtts          # narration
    pip install pydub         # music mixing (also needs ffmpeg)

ffmpeg (required by moviepy & pydub):
    Ubuntu/Debian : sudo apt-get install ffmpeg
    macOS         : brew install ffmpeg
    Windows       : https://ffmpeg.org/download.html
"""

from __future__ import annotations

import io
import os
import math
import tempfile
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── optional heavy deps ────────────────────────────────────────────────────────
try:
    # MoviePy v1 style
    from moviepy.editor import (
        VideoClip, AudioFileClip, CompositeAudioClip,
        concatenate_videoclips, concatenate_audioclips,
        ImageClip, VideoFileClip,
    )
    MOVIEPY_OK = True
except ImportError:
    try:
        # MoviePy v2 style
        from moviepy import (
            VideoClip, AudioFileClip, CompositeAudioClip,
            ImageClip, VideoFileClip,
            concatenate_videoclips, concatenate_audioclips
        )
        import moviepy
        print(f"[Info] Using MoviePy v{moviepy.__version__}")
        MOVIEPY_OK = True
    except ImportError:
        MOVIEPY_OK = False
        print("[WARN] moviepy not installed — install with: pip install moviepy")

try:
    from gtts import gTTS
    GTTS_OK = True
except ImportError:
    GTTS_OK = False
    print("[INFO] gTTS not installed — narration disabled. Install: pip install gtts")

try:
    from pydub import AudioSegment
    PYDUB_OK = True
except ImportError:
    PYDUB_OK = False


# ══════════════════════════════════════════════════════════════════════════════
# THEME REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

THEMES: dict[str, dict] = {
    'corporate': {
        'bg_top':         (15,  32,  75),
        'bg_bottom':      (30,  58, 138),
        'accent':         (96, 165, 250),
        'accent2':        (251, 191,  36),
        'text_primary':   (255, 255, 255),
        'text_secondary': (203, 213, 225),
        'card_bg':        (30,  41,  59),
        'card_border':    (96, 165, 250),
        'chart_colors':   ['#60a5fa','#fbbf24','#34d399','#f87171','#a78bfa','#fb7185'],
        'mpl_style':      'dark_background',
    },
    'vibrant': {
        'bg_top':         (17,  24,  39),
        'bg_bottom':      (31,  14,  77),
        'accent':         (167,  52, 235),
        'accent2':        (245,  87,  61),
        'text_primary':   (255, 255, 255),
        'text_secondary': (209, 213, 219),
        'card_bg':        (31,  41,  55),
        'card_border':    (167,  52, 235),
        'chart_colors':   ['#a734eb','#f5573d','#10b981','#f59e0b','#3b82f6','#ec4899'],
        'mpl_style':      'dark_background',
    },
    'dark': {
        'bg_top':         ( 9,   9,  11),
        'bg_bottom':      (24,  24,  27),
        'accent':         (16, 185, 129),
        'accent2':        (245, 158,  11),
        'text_primary':   (255, 255, 255),
        'text_secondary': (161, 161, 170),
        'card_bg':        (24,  24,  27),
        'card_border':    (16, 185, 129),
        'chart_colors':   ['#10b981','#f59e0b','#6366f1','#ef4444','#8b5cf6','#06b6d4'],
        'mpl_style':      'dark_background',
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# VIDEO DIMENSIONS
# ══════════════════════════════════════════════════════════════════════════════

W, H   = 1920, 1080
FPS    = 30
MARGIN = 80


# ══════════════════════════════════════════════════════════════════════════════
# FONT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf' if bold else
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
        '/Windows/Fonts/arial.ttf',
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.Draw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _wrap_text(text: str, draw: ImageDraw.Draw, font, max_width: int) -> list[str]:
    words = text.split()
    lines, current = [], ''
    for word in words:
        test = (current + ' ' + word).strip()
        w, _ = _text_size(draw, test, font)
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


# ══════════════════════════════════════════════════════════════════════════════
# GRADIENT BACKGROUND
# ══════════════════════════════════════════════════════════════════════════════

def _gradient_bg(theme: dict, width: int = W, height: int = H) -> Image.Image:
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)
    top, bot = theme['bg_top'], theme['bg_bottom']
    for y in range(height):
        t = y / height
        r = int(top[0] + t * (bot[0] - top[0]))
        g = int(top[1] + t * (bot[1] - top[1]))
        b = int(top[2] + t * (bot[2] - top[2]))
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return img


def _accent_bar(img: Image.Image, theme: dict, y: int = H - 8, height: int = 8):
    draw = ImageDraw.Draw(img)
    acc, acc2 = theme['accent'], theme['accent2']
    for x in range(W):
        t = x / W
        r = int(acc[0] + t * (acc2[0] - acc[0]))
        g = int(acc[1] + t * (acc2[1] - acc[1]))
        b = int(acc[2] + t * (acc2[2] - acc[2]))
        draw.line([(x, y), (x, y + height - 1)], fill=(r, g, b))
    return img


# ══════════════════════════════════════════════════════════════════════════════
# CHART RENDERING
# ══════════════════════════════════════════════════════════════════════════════

def _mpl_to_pil(fig: plt.Figure) -> Image.Image:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight',
                facecolor=fig.get_facecolor(), dpi=150)
    buf.seek(0)
    return Image.open(buf).copy()


def _chart_area() -> tuple[int, int, int, int]:
    x = MARGIN
    y = 200
    cw = W - 2 * MARGIN
    ch = H - y - 120
    return x, y, cw, ch


def _setup_axes(theme: dict, figsize=(16, 7)) -> tuple[plt.Figure, plt.Axes]:
    plt.style.use(theme.get('mpl_style', 'dark_background'))
    fig, ax = plt.subplots(figsize=figsize)
    bg = tuple(c / 255 for c in theme['bg_bottom'])
    fig.patch.set_facecolor(bg)
    ax.set_facecolor(tuple(c / 255 for c in theme['card_bg']))
    for spine in ax.spines.values():
        spine.set_edgecolor(tuple(c / 255 for c in theme['text_secondary']))
        spine.set_linewidth(0.5)
    ax.tick_params(colors=tuple(c / 255 for c in theme['text_secondary']), labelsize=13)
    ax.xaxis.label.set_color(tuple(c / 255 for c in theme['text_secondary']))
    ax.yaxis.label.set_color(tuple(c / 255 for c in theme['text_secondary']))
    return fig, ax


# ══════════════════════════════════════════════════════════════════════════════
# SLIDE COMPOSERS
# ══════════════════════════════════════════════════════════════════════════════

class SlideComposer:

    def __init__(self, theme: dict):
        self.t = theme

    def _base(self) -> tuple[Image.Image, ImageDraw.Draw]:
        img = _gradient_bg(self.t)
        _accent_bar(img, self.t)
        draw = ImageDraw.Draw(img)
        return img, draw

    def _draw_title_block(self, draw, title: str, subtitle: str | None,
                          title_y: int = 60, scale: float = 1.0, alpha: float = 1.0):
        title_size = max(20, int(90 * scale))
        sub_size   = max(14, int(48 * scale))
        font_title = _load_font(title_size, bold=True)
        font_sub   = _load_font(sub_size)

        tw, th = _text_size(draw, title, font_title)
        tx = (W - tw) // 2
        ty = title_y

        alpha_v   = int(255 * min(1.0, max(0.0, alpha)))
        col_title = (*self.t['text_primary'],   alpha_v)
        col_sub   = (*self.t['text_secondary'], alpha_v)

        draw.text((tx + 3, ty + 3), title, font=font_title, fill=(0, 0, 0, int(alpha_v * 0.5)))
        draw.text((tx, ty), title, font=font_title, fill=col_title)

        if subtitle:
            sw, sh = _text_size(draw, subtitle, font_sub)
            sx = (W - sw) // 2
            sy = ty + th + 20
            draw.text((sx + 2, sy + 2), subtitle, font=font_sub, fill=(0, 0, 0, int(alpha_v * 0.4)))
            draw.text((sx, sy), subtitle, font=font_sub, fill=col_sub)

    def _draw_section_title(self, draw, title: str):
        font = _load_font(52, bold=True)
        tw, _ = _text_size(draw, title, font)
        x = (W - tw) // 2
        acc = (*self.t['accent'], 255)
        draw.text((x + 2, 42), title, font=font, fill=(0, 0, 0, 160))
        draw.text((x, 40), title, font=font, fill=acc)
        draw.line([(x, 105), (x + tw, 105)], fill=acc, width=4)

    def _embed_chart(self, img: Image.Image, chart_img: Image.Image, progress: float = 1.0):
        cx, cy, cw, ch = _chart_area()
        chart = chart_img.resize((cw, ch), Image.LANCZOS)
        if progress < 1.0:
            reveal_w = max(1, int(cw * progress))
            chart = chart.crop((0, 0, reveal_w, ch))
            img.paste(chart, (cx, cy))
        else:
            img.paste(chart, (cx, cy))
        return img

    # ── slide types ────────────────────────────────────────────────────────────

    def title_slide(self, title: str, subtitle: str, progress: float = 1.0) -> Image.Image:
        img, draw = self._base()
        acc = self.t['accent']
        stripe_w = int(W * progress)
        draw.rectangle([0, H // 2 - 3, stripe_w, H // 2 + 3], fill=acc)
        scale = 0.4 + 0.6 * _ease_out(progress)
        alpha = progress
        self._draw_title_block(draw, title, subtitle,
                               title_y=int(H * 0.32), scale=scale, alpha=alpha)
        if progress > 0.5:
            a = int(255 * (progress - 0.5) * 2)
            draw.rectangle([MARGIN, H - 130, MARGIN + 300, H - 90], fill=(*acc, a))
            font_tag = _load_font(28)
            draw.text((MARGIN + 16, H - 122), 'ANALYTICS REPORT', font=font_tag,
                      fill=(*self.t['text_primary'], a))
        return img

    def chart_slide(self, title: str, chart_img: Image.Image, progress: float = 1.0) -> Image.Image:
        img, draw = self._base()
        self._draw_section_title(draw, title)
        self._embed_chart(img, chart_img, progress)
        return img

    def insight_slide(self, text: str, progress: float = 1.0) -> Image.Image:
        img, draw = self._base()
        alpha = int(255 * _ease_out(progress))

        margin = 200
        card_y = H // 2 - 130
        card_h = 260
        _draw_rounded_rect(draw,
                           [margin, card_y, W - margin, card_y + card_h],
                           radius=24,
                           fill=(*self.t['card_bg'], alpha),
                           outline=(*self.t['accent'], alpha),
                           outline_width=4)

        font = _load_font(56, bold=True)
        max_w = W - 2 * margin - 80
        lines = _wrap_text(text, draw, font, max_w)
        line_h = 68
        total_h = len(lines) * line_h
        start_y = card_y + (card_h - total_h) // 2

        slide_offset = int((1 - _ease_out(progress)) * 60)
        for i, line in enumerate(lines):
            lw, _ = _text_size(draw, line, font)
            lx = (W - lw) // 2
            ly = start_y + i * line_h + slide_offset
            draw.text((lx + 2, ly + 2), line, font=font, fill=(0, 0, 0, int(alpha * 0.5)))
            draw.text((lx, ly), line, font=font, fill=(*self.t['text_primary'], alpha))
        return img

    def summary_slide(self, metrics: list[dict], progress: float = 1.0) -> Image.Image:
        img, draw = self._base()
        font_h = _load_font(58, bold=True)
        draw.text((MARGIN, 40), 'Summary', font=font_h, fill=(*self.t['accent'], 255))

        n = len(metrics)
        cols = min(n, 3)
        rows = math.ceil(n / cols)
        card_w = (W - 2 * MARGIN - (cols - 1) * 40) // cols
        card_h = (H - 220 - (rows - 1) * 40) // rows

        for i, m in enumerate(metrics):
            col = i % cols
            row = i // cols
            cx = MARGIN + col * (card_w + 40)
            cy = 180 + row * (card_h + 40)
            alpha = int(255 * _ease_out(max(0, progress - i * 0.08)))
            _draw_rounded_rect(draw,
                               [cx, cy, cx + card_w, cy + card_h],
                               radius=16,
                               fill=(*self.t['card_bg'], alpha),
                               outline=(*self.t['accent'], alpha),
                               outline_width=3)
            if alpha < 10:
                continue
            fv = _load_font(64, bold=True)
            fl = _load_font(30)
            fd = _load_font(34, bold=True)
            vw, _ = _text_size(draw, m.get('value', ''), fv)
            draw.text((cx + (card_w - vw) // 2, cy + 30), m.get('value', ''), font=fv,
                      fill=(*self.t['text_primary'], alpha))
            lw, _ = _text_size(draw, m.get('label', ''), fl)
            draw.text((cx + (card_w - lw) // 2, cy + 110), m.get('label', ''), font=fl,
                      fill=(*self.t['text_secondary'], alpha))
            delta = m.get('delta', '')
            if delta:
                col_d = (52, 211, 153, alpha) if str(delta).startswith('+') else (248, 113, 113, alpha)
                dw, _ = _text_size(draw, delta, fd)
                draw.text((cx + (card_w - dw) // 2, cy + card_h - 60), delta, font=fd, fill=col_d)
        return img


# ══════════════════════════════════════════════════════════════════════════════
# CHART BUILDERS
# ══════════════════════════════════════════════════════════════════════════════

class ChartBuilder:

    def __init__(self, theme: dict):
        self.t = theme

    def bar(self, data: pd.DataFrame, x: str, y: str) -> Image.Image:
        fig, ax = _setup_axes(self.t)
        colors = self.t['chart_colors']
        bars = ax.bar(data[x], data[y],
                      color=[colors[i % len(colors)] for i in range(len(data))],
                      edgecolor='white', linewidth=0.4, width=0.6)
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, h + h * 0.01,
                    f'{h:,.0f}', ha='center', va='bottom', fontsize=13,
                    color='white', fontweight='bold')
        ax.set_xlabel(x, fontsize=14)
        ax.set_ylabel(y, fontsize=14)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:,.0f}'))
        ax.grid(axis='y', alpha=0.25, linestyle='--')
        fig.tight_layout()
        pil = _mpl_to_pil(fig)
        plt.close(fig)
        return pil

    def line(self, data: pd.DataFrame, x: str, y_cols: list[str]) -> Image.Image:
        fig, ax = _setup_axes(self.t)
        colors = self.t['chart_colors']
        for i, col in enumerate(y_cols):
            c = colors[i % len(colors)]
            ax.plot(data[x], data[col], marker='o', linewidth=3,
                    markersize=9, color=c, label=col)
            ax.fill_between(range(len(data)), data[col], alpha=0.12, color=c)
        ax.set_xlabel(x, fontsize=14)
        ax.tick_params(axis='x', labelsize=13)
        ax.legend(fontsize=13,
                  facecolor=tuple(c / 255 for c in self.t['card_bg']),
                  edgecolor='none', labelcolor='white')
        ax.grid(alpha=0.2, linestyle='--')
        ax.set_xticks(range(len(data)))
        ax.set_xticklabels(data[x].tolist(), rotation=0)
        fig.tight_layout()
        pil = _mpl_to_pil(fig)
        plt.close(fig)
        return pil

    def pie(self, data: pd.DataFrame, labels_col: str, values_col: str) -> Image.Image:
        fig, ax = _setup_axes(self.t, figsize=(10, 7))
        colors = self.t['chart_colors'][:len(data)]
        wedges, texts, autotexts = ax.pie(
            data[values_col], labels=data[labels_col], colors=colors,
            autopct='%1.1f%%', startangle=140, pctdistance=0.78,
            wedgeprops=dict(edgecolor='white', linewidth=1.5),
        )
        for t in texts:
            t.set_color('white'); t.set_fontsize(14)
        for at in autotexts:
            at.set_color('white'); at.set_fontsize(12); at.set_fontweight('bold')
        ax.set_aspect('equal')
        fig.tight_layout()
        pil = _mpl_to_pil(fig)
        plt.close(fig)
        return pil

    def scatter(self, data: pd.DataFrame, x: str, y: str,
                color_col: str | None = None, size_col: str | None = None) -> Image.Image:
        fig, ax = _setup_axes(self.t)
        colors = self.t['chart_colors']
        if color_col and color_col in data.columns:
            cats = data[color_col].unique()
            for i, cat in enumerate(cats):
                mask = data[color_col] == cat
                sz = data.loc[mask, size_col] * 2 if size_col and size_col in data.columns else 80
                ax.scatter(data.loc[mask, x], data.loc[mask, y],
                           c=colors[i % len(colors)], label=str(cat),
                           s=sz, alpha=0.8, edgecolors='white', linewidth=0.5)
            ax.legend(fontsize=12,
                      facecolor=tuple(c / 255 for c in self.t['card_bg']),
                      edgecolor='none', labelcolor='white')
        else:
            sz = data[size_col] * 2 if size_col and size_col in data.columns else 80
            ax.scatter(data[x], data[y], c=colors[0], s=sz, alpha=0.8,
                       edgecolors='white', linewidth=0.5)
        ax.set_xlabel(x, fontsize=14); ax.set_ylabel(y, fontsize=14)
        ax.grid(alpha=0.2, linestyle='--')
        fig.tight_layout()
        pil = _mpl_to_pil(fig)
        plt.close(fig)
        return pil

    def horizontal_bar(self, data: pd.DataFrame, x: str, y: str) -> Image.Image:
        fig, ax = _setup_axes(self.t)
        colors = self.t['chart_colors']
        ax.barh(data[x], data[y],
                color=[colors[i % len(colors)] for i in range(len(data))],
                edgecolor='white', linewidth=0.4)
        for i, v in enumerate(data[y]):
            ax.text(v + v * 0.01, i, f'{v:,.0f}',
                    va='center', ha='left', fontsize=13, color='white', fontweight='bold')
        ax.set_xlabel(y, fontsize=14)
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:,.0f}'))
        ax.grid(axis='x', alpha=0.25, linestyle='--')
        fig.tight_layout()
        pil = _mpl_to_pil(fig)
        plt.close(fig)
        return pil


# ══════════════════════════════════════════════════════════════════════════════
# EASING
# ══════════════════════════════════════════════════════════════════════════════

def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4 * t ** 3
    return 1 - (-2 * t + 2) ** 3 / 2


# ══════════════════════════════════════════════════════════════════════════════
# DRAWING UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def _draw_rounded_rect(draw: ImageDraw.Draw, xy: list[int], radius: int = 16,
                       fill=None, outline=None, outline_width: int = 2):
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill,
                               outline=outline, width=outline_width)
    except AttributeError:
        draw.rectangle(xy, fill=fill, outline=outline, width=outline_width)


# ══════════════════════════════════════════════════════════════════════════════
# NARRATION  (gTTS)
# ══════════════════════════════════════════════════════════════════════════════

def _narration_text_for_section(section: dict) -> str:
    """Auto-generate a narration script from a section config."""
    stype = section.get('type', '')
    if stype == 'title':
        parts = [section.get('title', ''), section.get('subtitle', '')]
        return '. '.join(p for p in parts if p)
    elif stype == 'bar':
        title = section.get('title', 'bar chart')
        data  = section.get('data')
        y     = section.get('y', '')
        extra = ''
        if data is not None and y in data.columns:
            top = data.nlargest(1, y)
            if len(top):
                extra = (f" The highest value is {top[y].iloc[0]:,.0f} "
                         f"for {top[section.get('x','')].iloc[0]}.")
        return f"Here is the {title}.{extra}"
    elif stype == 'line':
        return f"This line chart shows the {section.get('title', 'trend')} over time."
    elif stype == 'pie':
        return f"The pie chart breaks down {section.get('title', 'distribution')} by share."
    elif stype == 'scatter':
        return (f"This scatter plot compares {section.get('x','X')} "
                f"against {section.get('y','Y')}.")
    elif stype == 'hbar':
        return f"The horizontal bar chart shows {section.get('title', 'values')} per category."
    elif stype == 'insight':
        import re
        text = section.get('text', '')
        return re.sub(r'[^\x00-\x7F]', '', text).strip()  # strip emojis for TTS
    elif stype == 'summary':
        metrics = section.get('metrics', [])
        if metrics:
            parts = [f"{m.get('label','')} is {m.get('value','')}" for m in metrics[:3]]
            return "Summary. " + ". ".join(parts) + "."
        return "Here is the executive summary."
    return ''


def _generate_narration(text: str, output_path: str, lang: str = 'en') -> bool:
    """Synthesise narration MP3 via gTTS. Returns True on success."""
    if not GTTS_OK:
        return False
    if not text.strip():
        return False
    try:
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.save(output_path)
        return True
    except Exception as e:
        print(f"[WARN] Narration failed for text '{text[:40]}…': {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# BACKGROUND MUSIC
# ══════════════════════════════════════════════════════════════════════════════

def _loop_audio_to_duration(audio: 'AudioFileClip', duration: float,
                             fade_out_sec: float = 3.0) -> 'AudioFileClip':
    """Loop an audio clip to fill `duration` seconds, then fade out."""
    if audio.duration < duration:
        # loop by concatenating
        # using top-level concatenate_audioclips
        reps = int(duration / audio.duration) + 2
        looped = concatenate_audioclips([audio] * reps)
        audio = looped
    # subclip -> subclipped, audio_fadeout -> fadeout/with_fadeout
    if hasattr(audio, 'subclipped'):
        audio = audio.subclipped(0, duration)
    else:
        audio = audio.subclip(0, duration)

    if hasattr(audio, 'with_fadeout'):
        return audio.with_fadeout(fade_out_sec)
    elif hasattr(audio, 'audio_fadeout'):
        return audio.audio_fadeout(fade_out_sec)
    else:
        return audio.fadeout(fade_out_sec)


def _mix_background_music(
        video_path: str,
        music_path: str,
        output_path: str,
        music_volume: float = 0.15,
        fade_out_sec: float = 3.0,
) -> str:
    """
    Overlay background music on a video file.

    Parameters
    ----------
    video_path    : input MP4
    music_path    : background MP3 / WAV
    output_path   : output MP4 with mixed audio
    music_volume  : 0.0 – 1.0  (relative to original audio)
    fade_out_sec  : seconds for music fade-out at end

    Returns path of output file (video_path if mixing failed).
    """
    if not MOVIEPY_OK:
        print("[WARN] moviepy not available — skipping music mix")
        return video_path
    if not os.path.exists(music_path):
        print(f"[WARN] Music file not found: {music_path}")
        return video_path

    try:
        # using top-level imports

        print(f"[Music] Mixing {Path(music_path).name} into video …")
        video    = VideoFileClip(video_path)
        total    = video.duration
        bg_audio = AudioFileClip(music_path)
        if hasattr(bg_audio, 'with_volume_scaled'):
            bg_audio = bg_audio.with_volume_scaled(music_volume)
        else:
            bg_audio = bg_audio.volumex(music_volume)
        bg_audio = _loop_audio_to_duration(bg_audio, total, fade_out_sec)

        if video.audio:
            final_audio = CompositeAudioClip([video.audio, bg_audio])
        else:
            final_audio = bg_audio

        if hasattr(video, 'with_audio'):
            out = video.with_audio(final_audio)
        else:
            out = video.set_audio(final_audio)
        out.write_videofile(output_path, fps=FPS,
                            codec='libx264', audio_codec='aac', logger=None)
        video.close()
        bg_audio.close()
        print(f"[Music] Mixed → {output_path}")
        return output_path
    except Exception as e:
        print(f"[WARN] Music mixing failed: {e}")
        return video_path


# ══════════════════════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

class VideoReportGenerator:
    """
    Generate story-style analytics video reports.

    Parameters
    ----------
    theme : 'corporate' | 'vibrant' | 'dark'
    fps   : frames per second (default 30)
    """

    def __init__(self, theme: str = 'corporate', fps: int = FPS):
        if theme not in THEMES:
            raise ValueError(f"Unknown theme '{theme}'. Choose: {list(THEMES)}")
        self.theme_name = theme
        self.theme      = THEMES[theme]
        self.fps        = fps
        self._slide     = SlideComposer(self.theme)
        self._chart     = ChartBuilder(self.theme)

    # ── public API ─────────────────────────────────────────────────────────────

    def generate_report(
        self,
        config: dict,
        output_file: str = 'report.mp4',
        music_file:  str | None = None,
        music_volume: float = 0.15,
        narrate: bool = False,
        narration_lang: str = 'en',
        csv_path: str | None = None,
    ) -> str:
        """
        Build and save the video.

        Parameters
        ----------
        config         : report config dict
        output_file    : output MP4 path
        music_file     : path to background MP3/WAV  (None = no music)
        music_volume   : background music volume 0.0–1.0  (default 0.15)
        narrate        : synthesise per-section narration via gTTS
        narration_lang : BCP-47 lang code for gTTS (default 'en')
        csv_path       : if given, auto-extract insights from CSV and
                         prepend them to config['sections']

        Returns
        -------
        Absolute path of the final rendered file.
        """
        if not MOVIEPY_OK:
            raise RuntimeError("moviepy is required: pip install moviepy")

        # ── CSV auto-insights ─────────────────────────────────────────────────
        if csv_path:
            from insights_extractor import extract_insights
            print(f"[VideoReport] Auto-analysing CSV: {csv_path}")
            insight_result = extract_insights(csv_path)
            # merge: CSV sections replace/extend existing sections
            existing = config.get('sections', [])
            # keep any manually-specified title section if present
            manual_title = [s for s in existing if s.get('type') == 'title']
            csv_sections  = [s for s in insight_result['sections']
                             if s.get('type') != 'title']
            config['sections'] = (manual_title or insight_result['sections'][:1]) + csv_sections
            config.setdefault('title', insight_result['title'])
            config.setdefault('subtitle', insight_result['subtitle'])

        sections = config.get('sections', [])
        print(f"[VideoReport] Building {len(sections)} sections …")

        clips: list = []
        tmp_files: list[str] = []

        for idx, section in enumerate(sections):
            stype    = section.get('type', 'insight')
            duration = float(section.get('duration', 5))
            label    = (section.get('title') or section.get('text') or stype)[:50]
            print(f"  [{idx + 1}/{len(sections)}] {stype}: {label}")

            # ── narration ─────────────────────────────────────────────────────
            audio_clip = None
            if narrate:
                if not GTTS_OK:
                    print("[WARN] gTTS not installed — skipping narration. "
                          "Install: pip install gtts")
                else:
                    script = _narration_text_for_section(section)
                    if script:
                        narr_path = os.path.join(
                            tempfile.gettempdir(), f'narr_{idx}.mp3')
                        if _generate_narration(script, narr_path, narration_lang):
                            tmp_files.append(narr_path)
                            try:
                                audio_clip = AudioFileClip(narr_path)
                                # extend slide so narration fits
                                duration = max(duration, audio_clip.duration + 0.8)
                            except Exception as e:
                                print(f"[WARN] Could not load narration clip: {e}")
                                audio_clip = None

            # ── build video clip ──────────────────────────────────────────────
            clip = self._build_clip(section, duration)
            if audio_clip is not None:
                # pad or trim narration to exactly match clip duration
                if audio_clip.duration > duration:
                    if hasattr(audio_clip, 'subclipped'):
                        audio_clip = audio_clip.subclipped(0, duration)
                    else:
                        audio_clip = audio_clip.subclip(0, duration)
                
                if hasattr(clip, 'with_audio'):
                    clip = clip.with_audio(audio_clip)
                else:
                    clip = clip.set_audio(audio_clip)

            clips.append(clip)

        if not clips:
            raise ValueError("No sections produced clips.")

        final    = concatenate_videoclips(clips, method='compose')
        final    = self._add_intro_fade(final)
        out_path = str(Path(output_file).resolve())

        print(f"[VideoReport] Rendering → {out_path}")
        final.write_videofile(out_path, fps=self.fps,
                              codec='libx264', audio_codec='aac',
                              logger='bar')

        # clean temp narration files
        for f in tmp_files:
            try:
                os.remove(f)
            except Exception:
                pass

        # ── background music ──────────────────────────────────────────────────
        if music_file:
            mixed_path = out_path.replace('.mp4', '_with_music.mp4')
            out_path = _mix_background_music(
                out_path, music_file, mixed_path,
                music_volume=music_volume,
                fade_out_sec=3.0,
            )

        return out_path

    # ── clip builders ──────────────────────────────────────────────────────────

    def _build_clip(self, section: dict, duration: float):
        stype = section.get('type', 'insight')
        # dispatch = {
        #     'title':   self._title_clip,
        #     'bar':     lambda s, d: self._chart_clip(s, d, 'bar'),
        #     'line':    lambda s, d: self._chart_clip(s, d, 'line'),
        #     'pie':     lambda s, d: self._chart_clip(s, d, 'pie'),
        #     'scatter': lambda s, d: self._chart_clip(s, d, 'scatter'),
        #     'hbar':    lambda s, d: self._chart_clip(s, d, 'hbar'),
        #     'insight': self._insight_clip,
        #     'summary': self._summary_clip,
        # }
        dispatch = {
            'title':   self._title_clip,
            'bar':     lambda s, d: self._chart_clip(s, d, 'bar'),
            'line':    lambda s, d: self._chart_clip(s, d, 'line'),
            'pie':     lambda s, d: self._chart_clip(s, d, 'pie'),
            # 'scatter': lambda s, d: self._chart_clip(s, d, 'scatter'),  # skipped
            'hbar':    lambda s, d: self._chart_clip(s, d, 'hbar'),
            'insight': self._insight_clip,
            'summary': self._summary_clip,
        }
        builder = dispatch.get(stype)
        if builder is None:
            print(f"[WARN] Unknown section type '{stype}' — rendering as insight")
            builder = self._insight_clip
        return builder(section, duration)

    def _pil_to_np(self, img: Image.Image) -> np.ndarray:
        return np.array(img.convert('RGB'))

    def _title_clip(self, section: dict, duration: float):
        title    = section.get('title', 'Report')
        subtitle = section.get('subtitle', '')
        anim_dur = min(1.2, duration * 0.3)

        def make_frame(t):
            progress = min(1.0, t / anim_dur) if anim_dur > 0 else 1.0
            return self._pil_to_np(self._slide.title_slide(title, subtitle, progress))

        return VideoClip(make_frame, duration=duration)

    def _chart_clip(self, section: dict, duration: float, chart_type: str):
        title    = section.get('title', chart_type.title() + ' Chart')
        anim_dur = min(1.5, duration * 0.4)
        data     = section.get('data')
        chart_img = self._render_chart(chart_type, section, data)

        def make_frame(t):
            progress = _ease_out(min(1.0, t / anim_dur)) if anim_dur > 0 else 1.0
            return self._pil_to_np(self._slide.chart_slide(title, chart_img, progress))

        return VideoClip(make_frame, duration=duration)

    def _insight_clip(self, section: dict, duration: float):
        text     = section.get('text', '')
        anim_dur = min(0.8, duration * 0.3)

        def make_frame(t):
            progress = _ease_out(min(1.0, t / anim_dur)) if anim_dur > 0 else 1.0
            return self._pil_to_np(self._slide.insight_slide(text, progress))

        return VideoClip(make_frame, duration=duration)

    def _summary_clip(self, section: dict, duration: float):
        metrics  = section.get('metrics', [])
        anim_dur = min(2.0, duration * 0.5)

        def make_frame(t):
            progress = _ease_out(min(1.0, t / anim_dur)) if anim_dur > 0 else 1.0
            return self._pil_to_np(self._slide.summary_slide(metrics, progress))

        return VideoClip(make_frame, duration=duration)


    def _render_chart(self, chart_type: str, section: dict,
                    data: pd.DataFrame | None):
        try:
            if data is None:
                raise ValueError("No data for chart")

            if chart_type == 'bar':
                return self._chart.bar(data, section['x'], section['y'])

            elif chart_type == 'line':
                return self._chart.line(data, section['x'],
                                        section.get('y_cols', [section.get('y', '')]))

            elif chart_type == 'pie':
                return self._chart.pie(data, section['labels'], section['values'])

            elif chart_type == 'scatter':
                return self._chart.scatter(
                    data,
                    section['x'],
                    section['y'],
                    section.get('color'),
                    section.get('size')
                )

            elif chart_type == 'hbar':
                return self._chart.horizontal_bar(data, section['x'], section['y'])

            else:
                raise ValueError(f"Unknown chart type: {chart_type}")

        except Exception as e:
            print(f"[ChartBuilder] Skipping chart due to error: {e}")

            # Return blank image instead of crashing
            from PIL import Image
            return Image.new("RGB", (1280, 720), (30, 30, 30))

    @staticmethod
    def _add_intro_fade(clip, fade_sec: float = 0.4):
        try:
            if hasattr(clip, 'with_fadein'):
                return clip.with_fadein(fade_sec)
            from moviepy.video.fx.all import fadein
            return fadein(clip, fade_sec)
        except Exception:
            try:
                # possible v2 location
                from moviepy.video.fx.FadeIn import fadein
                return fadein(clip, fade_sec)
            except Exception:
                return clip
