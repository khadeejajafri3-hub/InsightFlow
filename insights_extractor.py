from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────
# GEMINI API
# ─────────────────────────────────────────────────────────────
GEMINI_AVAILABLE = False
try:
    import google.generativeai as genai
    # api_key = os.environ.get("GEMINI_API_KEY")
    api_key = 'AIzaSyDhwbVrWfHNq5yDSS2gm7YnftXePHAJCAM'
    print(api_key)
    if api_key:
        genai.configure(api_key=api_key)
        GEMINI_AVAILABLE = True
except Exception as e:
    print(f"[Gemini] Not available: {e}")
    GEMINI_AVAILABLE = False


def _gemini_analyse(df: pd.DataFrame) -> dict | None:
    if not GEMINI_AVAILABLE:
        return None

    try:
        preview = df.head(30).to_csv(index=False)
        stats = df.describe(include='all').to_string()

        prompt = f"""
You are a data analyst.

Dataset preview:
{preview}

Statistics:
{stats}

Columns: {list(df.columns)}
Rows: {len(df)}

Return ONLY JSON in this format:

{{
  "title": "Report title",
  "subtitle": "Short subtitle",
  "insights": ["insight 1", "insight 2"],
  "chart_configs": [
    {{
      "type": "bar|line|pie|scatter|hbar",
      "x_col": "column",
      "y_col": "column",
      "color_col": "optional column",
      "title": "Chart title",
      "duration": 6
    }}
  ],
  "kpi_metrics": [
    {{"label": "...", "value": "...", "delta": "..."}}
  ]
}}
Return ONLY JSON.
"""

        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        raw = response.text.strip()

        raw = raw.replace("```json", "").replace("```", "")
        return json.loads(raw)

    except Exception as e:
        print(f"[Gemini] Analysis failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# CLAUDE API (Fallback)
# ─────────────────────────────────────────────────────────────
try:
    import anthropic
    _ANTHROPIC_CLIENT = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", "")
    )
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False


def _claude_analyse(df: pd.DataFrame) -> dict | None:
    if not CLAUDE_AVAILABLE:
        return None

    try:
        preview = df.head(30).to_csv(index=False)
        stats = df.describe(include='all').to_string()

        prompt = f"""
CSV preview:
{preview}

Stats:
{stats}

Return JSON with title, subtitle, insights, chart_configs, kpi_metrics.
"""

        msg = _ANTHROPIC_CLIENT.messages.create(
            model="claude-opus-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = msg.content[0].text.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw)
        raw = re.sub(r'\n?```$', '', raw)
        return json.loads(raw)

    except Exception as e:
        print(f"[Claude] Analysis failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# HEURISTIC ANALYSER (Fallback)
# ─────────────────────────────────────────────────────────────
class HeuristicAnalyser:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.num_cols = df.select_dtypes(include='number').columns.tolist()
        self.cat_cols = df.select_dtypes(include='object').columns.tolist()

    def analyse(self):
        sections = []
        metrics = []

        if len(self.num_cols) >= 2:
            sections.append({
                'type': 'scatter',
                'data': self.df[[self.num_cols[0], self.num_cols[1]]].dropna(),
                'x': self.num_cols[0],
                'y': self.num_cols[1],
                'title': f'{self.num_cols[0]} vs {self.num_cols[1]}',
                'duration': 6,
            })

        if self.cat_cols and self.num_cols:
            grp = self.df.groupby(self.cat_cols[0])[self.num_cols[0]].sum().reset_index()
            sections.append({
                'type': 'bar',
                'data': grp,
                'x': self.cat_cols[0],
                'y': self.num_cols[0],
                'title': f'{self.num_cols[0]} by {self.cat_cols[0]}',
                'duration': 6,
            })

        for col in self.num_cols:
            metrics.append({
                'label': f'Total {col}',
                'value': f'{self.df[col].sum():,.0f}',
                'delta': f'avg {self.df[col].mean():,.0f}',
            })

        return {
            'sections': sections,
            'summary_metrics': metrics
        }


# ─────────────────────────────────────────────────────────────
# BUILD SECTIONS FROM AI JSON
# ─────────────────────────────────────────────────────────────
def _build_sections_from_ai(df: pd.DataFrame, ai_result: dict):
    sections = []

    # insights
    for text in ai_result.get('insights', []):
        sections.append({'type': 'insight', 'text': text, 'duration': 4})

    # charts
    for cfg in ai_result.get('chart_configs', []):
        try:
            chart_type = cfg.get('type', 'bar')
            x = cfg.get('x_col')
            y = cfg.get('y_col')
            color = cfg.get('color_col')

            # Check columns exist
            if x not in df.columns or y not in df.columns:
                print(f"[Extractor] Skipping chart — columns missing: {x}, {y}")
                continue

            sub = df[[x, y]].copy()

            # Convert numeric safely
            sub[y] = pd.to_numeric(sub[y], errors='coerce')
            sub = sub.dropna()

            if sub.empty:
                print(f"[Extractor] Skipping chart — no numeric data: {y}")
                continue

            # Add color column if exists
            if color and color in df.columns:
                sub[color] = df[color]

            sec = {
                'type': chart_type,
                'data': sub,
                'x': x,
                'y': y,
                'title': cfg.get('title', 'Chart'),
                'duration': cfg.get('duration', 6),
            }

            if color:
                sec['color'] = color

            sections.append(sec)

        except Exception as e:
            print(f"[Extractor] Skipping chart due to error: {e}")
            continue

    # summary
    kpis = ai_result.get('kpi_metrics', [])
    if kpis:
        sections.append({'type': 'summary', 'metrics': kpis, 'duration': 7})

    return sections

# ─────────────────────────────────────────────────────────────
# PUBLIC FUNCTION
# ─────────────────────────────────────────────────────────────
def extract_insights(
    csv_path: str,
    title: str | None = None,
):
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    print(f"[InsightExtractor] Loading {path.name} …")
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()

    # Try Gemini
    print("[InsightExtractor] Requesting Gemini analysis …")
    ai_result = _gemini_analyse(df)

    # Try Claude
    if not ai_result:
        print("[InsightExtractor] Gemini failed — trying Claude …")
        ai_result = _claude_analyse(df)

    # Fallback heuristic
    if not ai_result:
        print("[InsightExtractor] Using heuristic analysis ✓")
        analyser = HeuristicAnalyser(df)
        result = analyser.analyse()
        sections = result['sections']
        metrics = result['summary_metrics']
        report_title = title or path.stem
        report_subtitle = "Auto-generated Analytics Report"

    else:
        print("[InsightExtractor] Using AI-generated insights ✓")
        sections = _build_sections_from_ai(df, ai_result)
        metrics = ai_result.get('kpi_metrics', [])
        report_title = title or ai_result.get('title', path.stem)
        report_subtitle = ai_result.get('subtitle', "AI Analytics Report")

    # Add title slide
    title_section = {
        'type': 'title',
        'title': report_title,
        'subtitle': report_subtitle,
        'duration': 4,
    }

    sections = [title_section] + sections

    print(f"[InsightExtractor] Built {len(sections)} sections")

    return {
        'title': report_title,
        'subtitle': report_subtitle,
        'sections': sections,
        'summary_metrics': metrics,
        'dataframe': df,
    }