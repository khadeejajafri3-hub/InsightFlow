"""
main.py — Analytics Video Report Generator  (v2)
=================================================
New features
------------
  1. CSV auto-insights  — pass csv_path= to load any CSV and auto-generate
                          charts + insight cards + KPI summary
  2. Narration          — per-section AI voice via gTTS
  3. Background music   — any MP3/WAV with volume control + auto fade-out

Quick setup
-----------
    pip install moviepy pillow matplotlib numpy pandas gtts pydub
    sudo apt-get install ffmpeg          # Linux (needed by moviepy/pydub)
    # brew install ffmpeg                # macOS

Run
---
    python main.py
    python main.py --csv my_data.csv --music bg.mp3 --narrate --theme vibrant
"""

import argparse
import sys
import numpy as np
import pandas as pd

from generator import VideoReportGenerator


# ══════════════════════════════════════════════════════════════════════════════
# CLI ARGUMENT PARSER  (all settings can also be changed in-code below)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_args():
    p = argparse.ArgumentParser(description='Analytics Video Report Generator v2')
    p.add_argument('--csv',     metavar='FILE',  default=None,
                   help='Path to a CSV file for auto-insight extraction')
    p.add_argument('--music',   metavar='FILE',  default=None,
                   help='Background music MP3/WAV file')
    p.add_argument('--volume',  type=float,      default=0.15,
                   help='Background music volume 0.0–1.0 (default 0.15)')
    p.add_argument('--narrate', action='store_true',
                   help='Enable gTTS narration (requires: pip install gtts)')
    p.add_argument('--lang',    default='en',
                   help='Narration language BCP-47 code (default: en)')
    p.add_argument('--theme',   default='vibrant',
                   choices=['corporate', 'vibrant', 'dark'],
                   help='Visual theme (default: vibrant)')
    p.add_argument('--output',  default='analytics_report.mp4',
                   help='Output MP4 filename (default: analytics_report.mp4)')
    # allow unknown args so inline-config still works
    args, _ = p.parse_known_args()
    return args


args = _parse_args()

# ══════════════════════════════════════════════════════════════════════════════
# ── EDIT THESE to change defaults without using CLI flags ────────────────────
# ══════════════════════════════════════════════════════════════════════════════

CSV_FILE     = args.csv      or None   # e.g. "sales_data.csv"
MUSIC_FILE   = args.music    or None   # e.g. "bg_music.mp3"
MUSIC_VOLUME = args.volume             # 0.0 – 1.0
NARRATE      = args.narrate            # True / False
NARR_LANG    = args.lang               # 'en', 'hi', 'es', etc.
THEME        = args.theme              # 'corporate' | 'vibrant' | 'dark'
OUTPUT_FILE  = args.output

# ══════════════════════════════════════════════════════════════════════════════
# SAMPLE DATA  (used when no CSV is supplied)
# ══════════════════════════════════════════════════════════════════════════════

np.random.seed(42)

sales_data = pd.DataFrame({
    'Month':  ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
    'Sales':  [45000, 52000, 48000, 61000, 58000, 67000],
    'Profit': [12000, 15000, 13000, 18000, 17000, 21000],
    'Units':  [450,   520,   480,   610,   580,   670],
})

category_data = pd.DataFrame({
    'Category': ['Electronics', 'Clothing', 'Food', 'Books'],
    'Revenue':  [35000, 28000, 42000, 18000],
})

product_data = pd.DataFrame({
    'Product':  [f'P{i:02d}' for i in range(1, 21)],
    'Price':    np.round(np.random.uniform(10, 100, 20), 1),
    'Sales':    np.round(np.random.uniform(100, 1000, 20), 0),
    'Category': np.random.choice(['Electronics', 'Clothing', 'Food'], 20),
})

units_data = pd.DataFrame({
    'Month': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
    'Units': [450, 520, 480, 610, 580, 670],
})

# ══════════════════════════════════════════════════════════════════════════════
# MANUAL REPORT CONFIG  (used when no CSV is supplied)
# ══════════════════════════════════════════════════════════════════════════════

manual_config = {
    'title':    'Q2 2024 Sales Report',
    'subtitle': 'Performance Analysis & Insights',
    'theme':    THEME,

    'sections': [
        {
            'type':     'title',
            'title':    'Q2 2024 Sales Report',
            'subtitle': 'Performance Analysis & Insights',
            'duration': 4,
        },
        {
            'type':     'bar',
            'data':     sales_data,
            'x':        'Month',
            'y':        'Sales',
            'title':    'Monthly Sales Performance',
            'duration': 6,
        },
        {
            'type':     'insight',
            'text':     '📈 Sales surged 49% from Jan → Jun, reaching $67K!',
            'duration': 4,
        },
        {
            'type':     'line',
            'data':     sales_data,
            'x':        'Month',
            'y_cols':   ['Sales', 'Profit'],
            'title':    'Sales vs Profit Trend',
            'duration': 6,
        },
        {
            'type':     'pie',
            'data':     category_data,
            'labels':   'Category',
            'values':   'Revenue',
            'title':    'Revenue by Category',
            'duration': 5,
        },
        {
            'type':     'insight',
            'text':     '🍔 Food leads with 34% market share — highest in the portfolio',
            'duration': 4,
        },
        {
            'type':     'scatter',
            'data':     product_data,
            'x':        'Price',
            'y':        'Sales',
            'color':    'Category',
            'title':    'Price vs Sales by Category',
            'duration': 6,
        },
        {
            'type':     'hbar',
            'data':     units_data,
            'x':        'Month',
            'y':        'Units',
            'title':    'Units Sold per Month',
            'duration': 5,
        },
        {
            'type':    'summary',
            'metrics': [
                {'label': 'Total Revenue',   'value': '$331K', 'delta': '+49%'},
                {'label': 'Total Profit',    'value': '$96K',  'delta': '+75%'},
                {'label': 'Units Sold',      'value': '3,310', 'delta': '+49%'},
                {'label': 'Top Category',    'value': 'Food',  'delta': '34%'},
                {'label': 'Best Month',      'value': 'Jun',   'delta': '$67K'},
                {'label': 'Avg Monthly Rev', 'value': '$55K',  'delta': ''},
            ],
            'duration': 7,
        },
    ],
}

# ══════════════════════════════════════════════════════════════════════════════
# GENERATE
# ══════════════════════════════════════════════════════════════════════════════

print("=" * 62)
print("  ANALYTICS VIDEO REPORT GENERATOR  v2")
print("=" * 62)
print(f"  Theme     : {THEME}")
print(f"  CSV input : {CSV_FILE or '(none — using sample data)'}")
print(f"  Music     : {MUSIC_FILE or '(none)'}"
      + (f"  @ vol {MUSIC_VOLUME:.0%}" if MUSIC_FILE else ''))
print(f"  Narration : {'enabled (' + NARR_LANG + ')' if NARRATE else 'disabled'}")
print(f"  Output    : {OUTPUT_FILE}")
print("=" * 62)

generator = VideoReportGenerator(theme=THEME)

output_path = generator.generate_report(
    config         = manual_config,
    output_file    = OUTPUT_FILE,
    csv_path       = CSV_FILE,        # ← auto-insights from CSV
    music_file     = MUSIC_FILE,      # ← background music
    music_volume   = MUSIC_VOLUME,    # ← volume 0.0–1.0
    narrate        = NARRATE,         # ← gTTS narration
    narration_lang = NARR_LANG,
)

print("\n" + "=" * 62)
print(f"  ✅  Done!")
print(f"  📁  {output_path}")
print("=" * 62)

print("""
Usage examples
──────────────
# Auto-analyse a CSV file:
    python main.py --csv my_sales.csv

# Add background music (MP3/WAV):
    python main.py --music bg_music.mp3

# Enable narration:
    python main.py --narrate

# Full combo:
    python main.py --csv data.csv --music bg.mp3 --narrate --theme corporate

# Change volume (0.0 = silent, 1.0 = full):
    python main.py --music bg.mp3 --volume 0.2

# Hindi narration:
    python main.py --narrate --lang hi

CSV format tips
───────────────
  • Include a date/month/period column for time-series charts
  • Numeric columns → bar, line, scatter charts
  • Categorical columns → pie & grouped charts
  • Claude API (ANTHROPIC_API_KEY env var) gives smarter insights;
    falls back to heuristics automatically
""")
