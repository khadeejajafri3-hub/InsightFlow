"""
generator.py — VideoReportGenerator (Fast Matplotlib Edition)
=============================================================================
Dependencies: pip install moviepy pillow matplotlib pandas numpy gtts
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
matplotlib.use('Agg') # Force non-interactive backend for thread safety
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── optional heavy deps ────────────────────────────────────────────────────────
try:
    # Try MoviePy v1.x style
    from moviepy.editor import VideoClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips, ImageClip, VideoFileClip
    MOVIEPY_OK = True
except ImportError:
    try:
        # Try MoviePy v2.x style
        from moviepy import VideoClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips, ImageClip, VideoFileClip
        MOVIEPY_OK = True
    except ImportError:
        try:
            # Last ditch effort for specific v2 sub-modules
            from moviepy.video.VideoClip import VideoClip
            from moviepy.audio.AudioClip import AudioFileClip
            from moviepy.video.compositing.concatenate import concatenate_videoclips
            MOVIEPY_OK = True
        except ImportError:
            MOVIEPY_OK = False

if not MOVIEPY_OK:
    # Fallback to prevent NameError even if MOVIEPY_OK is checked later
    class VideoClip: pass
    class AudioFileClip: pass
    print("[CRITICAL] MoviePy not found. Please run: pip install moviepy")

try:
    from gtts import gTTS
    GTTS_OK = True
except ImportError:
    GTTS_OK = False

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
        'card_bg':        (30,  41,  59, 180),
        'chart_colors':   ['#60a5fa','#fbbf24','#34d399','#f87171','#a78bfa'],
    },
    'vibrant': {
        'bg_top':         (17,  24,  39),
        'bg_bottom':      (31,  14,  77),
        'accent':         (167,  52, 235),
        'accent2':        (245,  87,  61),
        'text_primary':   (255, 255, 255),
        'text_secondary': (209, 213, 219),
        'card_bg':        (31,  41,  55, 200),
        'chart_colors':   ['#a734eb','#f5573d','#10b981','#f59e0b','#3b82f6'],
    }
}

W, H   = 1920, 1080
FPS    = 24
MARGIN = 80

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = ['/Windows/Fonts/arialbd.ttf' if bold else '/Windows/Fonts/arial.ttf',
                  '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                  '/System/Library/Fonts/Helvetica.ttc']
    for path in candidates:
        if os.path.exists(path): return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def _text_size(draw: ImageDraw.Draw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def _wrap_text(text: str, draw: ImageDraw.Draw, font, max_width: int) -> list[str]:
    words = text.split(); lines, current = [], ''
    for word in words:
        test = (current + ' ' + word).strip()
        if _text_size(draw, test, font)[0] <= max_width: current = test
        else:
            if current: lines.append(current)
            current = word
    if current: lines.append(current)
    return lines

def _gradient_bg(theme: dict) -> Image.Image:
    img = Image.new('RGB', (W, H))
    draw = ImageDraw.Draw(img)
    top, bot = theme['bg_top'], theme['bg_bottom']
    for y in range(H):
        t = y / H
        r = int(top[0] + t * (bot[0] - top[0]))
        g = int(top[1] + t * (bot[1] - top[1]))
        b = int(top[2] + t * (bot[2] - top[2]))
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    return img

def _mpl_to_pil(fig) -> Image.Image:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', transparent=True, dpi=120)
    buf.seek(0)
    return Image.open(buf).copy()

def _ease_out(t: float) -> float:
    return 1 - (1 - max(0, min(1, t))) ** 3

def _draw_rounded_rect(draw, xy, radius=16, fill=None, outline=None, width=2):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

def _setup_axes(theme: dict, figsize=(10, 6)):
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=figsize, facecolor='none')
    ax.set_facecolor('none')
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.tick_params(colors='white', labelsize=12)
    return fig, ax

# ══════════════════════════════════════════════════════════════════════════════
# CLASSES
# ══════════════════════════════════════════════════════════════════════════════

class ChartBuilder:
    def __init__(self, theme: dict):
        self.t = theme

    def bar(self, data: pd.DataFrame, x: str, y: str, progress: float = 1.0) -> Image.Image:
        fig, ax = _setup_axes(self.t)
        vals = data[y] * progress
        bars = ax.bar(data[x], vals, color=self.t['chart_colors'], edgecolor='white', linewidth=1)
        ax.set_title(f"Total {y} by {x}", color='white', fontsize=18, pad=20)
        img = _mpl_to_pil(fig)
        plt.close(fig)
        return img

    def line(self, data: pd.DataFrame, x: str, y: list[str] | str, progress: float = 1.0) -> Image.Image:
        fig, ax = _setup_axes(self.t)
        if isinstance(y, str): y = [y]
        sub = data.head(max(2, int(len(data) * progress)))
        for i, col in enumerate(y):
            ax.plot(sub[x], sub[col], marker='o', linewidth=4, color=self.t['chart_colors'][i % 5])
            ax.fill_between(sub[x], sub[col], alpha=0.2, color=self.t['chart_colors'][i % 5])
        ax.set_title("Performance Trend", color='white', fontsize=18, pad=20)
        img = _mpl_to_pil(fig)
        plt.close(fig)
        return img

    def pie(self, data: pd.DataFrame, x: str, y: str, progress: float = 1.0) -> Image.Image:
        if progress < 0.01: return Image.new('RGBA', (W, H), (0,0,0,0))
        fig, ax = _setup_axes(self.t, figsize=(8, 8))
        vals = data[y] * progress
        # Ensure values sum > 0
        if vals.sum() <= 0: vals = [0.00001] * len(data)
        ax.pie(vals, labels=data[x], colors=self.t['chart_colors'], autopct='%1.1f%%', wedgeprops={'edgecolor': 'white', 'alpha': progress})
        ax.set_title("Distribution Analysis", color='white', fontsize=18)
        img = _mpl_to_pil(fig)
        plt.close(fig)
        return img

    def horizontal_bar(self, data: pd.DataFrame, x: str, y: str, progress: float = 1.0) -> Image.Image:
        fig, ax = _setup_axes(self.t)
        ax.barh(data[x], data[y] * progress, color=self.t['chart_colors'], edgecolor='white')
        ax.set_title(f"{y} Leaderboard", color='white', fontsize=18, pad=20)
        ax.invert_yaxis()
        img = _mpl_to_pil(fig)
        plt.close(fig)
        return img

class SlideComposer:
    def __init__(self, theme: dict):
        self.t = theme

    def _base(self) -> tuple[Image.Image, ImageDraw.Draw]:
        img = _gradient_bg(self.t)
        return img, ImageDraw.Draw(img, 'RGBA')

    def title_slide(self, title: str, subtitle: str, progress: float = 1.0) -> Image.Image:
        img, draw = self._base()
        f_t, f_s = _load_font(120, True), _load_font(60)
        alpha = int(255 * progress)
        tw, th = _text_size(draw, title, f_t)
        draw.text(((W-tw)//2, H//2-100), title, font=f_t, fill=(255,255,255,alpha))
        sw, _ = _text_size(draw, subtitle, f_s)
        draw.text(((W-sw)//2, H//2+th-50), subtitle, font=f_s, fill=(200,200,200,alpha))
        return img

    def chart_slide(self, title: str, chart_img: Image.Image, progress: float = 1.0) -> Image.Image:
        img, draw = self._base()
        font = _load_font(52, True)
        tw, _ = _text_size(draw, title, font)
        draw.text(((W-tw)//2, 60), title, font=font, fill=(*self.t['accent'], 255))
        chart = chart_img.resize((1400, 800), Image.LANCZOS)
        img.paste(chart, ((W-1400)//2, 200), chart)
        return img

    def insight_slide(self, text: str, progress: float = 1.0) -> Image.Image:
        img, draw = self._base()
        alpha = int(255 * _ease_out(progress))
        _draw_rounded_rect(draw, [250, 350, W-250, H-350], radius=40, fill=(*self.t['card_bg'][:3], alpha), outline=(*self.t['accent'], alpha))
        font = _load_font(65, True)
        lines = _wrap_text(text, draw, font, W-600)
        for i, line in enumerate(lines):
            lw, _ = _text_size(draw, line, font)
            draw.text(((W-lw)//2, 420 + i*90), line, font=font, fill=(255,255,255,alpha))
        return img

    def summary_slide(self, metrics: list[dict], progress: float = 1.0) -> Image.Image:
        img, draw = self._base()
        f_h = _load_font(80, True)
        draw.text((MARGIN, 80), 'EXECUTIVE RECAP', font=f_h, fill=(*self.t['accent'], 255))
        for i, m in enumerate(metrics[:4]):
            alpha = int(255 * _ease_out(progress * 1.5 - i*0.2))
            x, y = MARGIN + (i%2)*900, 300 + (i//2)*350
            _draw_rounded_rect(draw, [x, y, x+850, y+300], radius=30, fill=(20,20,20,alpha), outline=(*self.t['accent'], alpha))
            draw.text((x+50, y+50), str(m.get('value','')), font=_load_font(90,True), fill=(255,255,255,alpha))
            draw.text((x+50, y+160), str(m.get('label','')).upper(), font=_load_font(40), fill=(200,200,200,alpha))
        return img

class VideoReportGenerator:
    def __init__(self, theme: str = 'corporate'):
        self.theme = THEMES[theme]
        self._slide = SlideComposer(self.theme)
        self._chart = ChartBuilder(self.theme)

    def generate_report(self, config, output_file, music_file=None, music_volume=0.15, narrate=False, narration_lang='en', csv_path=None):
        if csv_path:
            from insights_extractor import extract_insights
            res = extract_insights(csv_path, title=config.get('title'))
            config['sections'] = res['sections'][:8] # Limit to 8
            config['title'] = res['title']
            config['summary_metrics'] = res.get('summary_metrics', [])
        
        sections = config.get('sections', [])
        clips = []
        
        for i, section in enumerate(sections):
            stype = section.get('type', 'insight')
            duration = 4.0
            
            def make_frame(t, dur=duration, sect=section, st=stype, idx=i):
                progress = _ease_out(t/dur)
                if st == 'title': return np.array(self._slide.title_slide(config.get('title','Report'), 'Insights Report', progress))
                if st in ['bar', 'line', 'pie', 'hbar']:
                    method_map = {'hbar': 'horizontal_bar', 'bar': 'bar', 'line': 'line', 'pie': 'pie'}
                    cimg = getattr(self._chart, method_map.get(st, st))(sect['data'], sect.get('x') or sect.get('labels'), sect.get('y') or sect.get('values'), progress)
                    return np.array(self._slide.chart_slide(sect.get('title','Chart'), cimg, progress))
                if st == 'insight': return np.array(self._slide.insight_slide(sect.get('text','Insight'), progress))
                return np.array(self._slide.summary_slide(config.get('summary_metrics', []), progress))
            
            print(f"[Renderer] Section {i+1}/{len(sections)}: {stype}")
            clips.append(VideoClip(make_frame, duration=duration))
        
        final = concatenate_videoclips(clips)
        
        # MUSIC MIXING
        if music_file:
            abs_music = os.path.abspath(music_file)
            if os.path.exists(abs_music):
                print(f"[Audio] Found music file: {abs_music}")
                try:
                    bg_music = AudioFileClip(abs_music)
                    
                    # Version-agnostic trimming
                    dur = min(bg_music.duration, final.duration)
                    if hasattr(bg_music, 'subclip'):
                        bg_music = bg_music.subclip(0, dur)
                    elif hasattr(bg_music, 'subclipped'):
                        bg_music = bg_music.subclipped(0, dur)
                    else:
                        bg_music = bg_music.set_duration(dur)
                    
                    # Version-agnostic volume
                    if hasattr(bg_music, 'volumex'):
                        bg_music = bg_music.volumex(music_volume)
                    elif hasattr(bg_music, 'multiply_volume'):
                        bg_music = bg_music.multiply_volume(music_volume)
                    
                    # Safe fadeout
                    if hasattr(bg_music, 'audio_fadeout'):
                        try: bg_music = bg_music.audio_fadeout(2)
                        except: pass
                    elif hasattr(bg_music, 'fadeout'):
                        try: bg_music = bg_music.fadeout(2)
                        except: pass
                    
                    # Version-agnostic audio attachment
                    if hasattr(final, 'set_audio'):
                        final = final.set_audio(bg_music)
                    elif hasattr(final, 'with_audio'):
                        final = final.with_audio(bg_music)
                    
                    print("[Audio] Successfully attached to video clip.")
                except Exception as e:
                    print(f"[Audio Error] Mixing failed: {e}")
            else:
                print(f"[Audio Error] Music file not found at: {abs_music}")
        
        print(f"[Renderer] Finalizing video: {output_file}")
        final.write_videofile(
            output_file, 
            fps=FPS, 
            codec='libx264', 
            audio_codec='aac', 
            temp_audiofile="temp-audio.m4a",
            remove_temp=True,
            logger='bar'
        )
        return output_file
