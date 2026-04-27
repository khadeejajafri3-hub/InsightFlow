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
# GEMINI API (Temporarily disabled - provide fresh key to re-enable)
GEMINI_AVAILABLE = False
# try:
#     import google.generativeai as genai
#     api_key = 'AIzaSyDhwbVrWfHNq5yDSS2gm7YnftXePHAJCAM'
#     if api_key:
#         genai.configure(api_key=api_key)
#         GEMINI_AVAILABLE = True
# except Exception as e:
#     GEMINI_AVAILABLE = False


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

        # 1. Start with a Hero Insight
        if self.num_cols:
            col = self.num_cols[0]
            total = self.df[col].sum()
            metrics.append({'label': f'Total {col}', 'value': f'{total:,.0f}', 'delta': 'Overall Volume'})
            
            # Peak Insight
            peak_idx = self.df[col].idxmax()
            peak_val = self.df.loc[peak_idx, col]
            peak_label = self.df.loc[peak_idx, self.cat_cols[0]] if self.cat_cols else f"Row {peak_idx}"
            sections.append({'type': 'insight', 'text': f'BOOM! Your peak {col} reached {peak_val:,.0f} with {peak_label}!', 'duration': 4})

        # 2. Generate multiple charts to reach 7-8 target
        # Chart 1: Bar Chart of first category
        if self.cat_cols and self.num_cols:
            grp = self.df.groupby(self.cat_cols[0])[self.num_cols[0]].sum().sort_values(ascending=False).reset_index()
            sections.append({
                'type': 'bar', 'data': grp.head(8), 'x': self.cat_cols[0], 'y': self.num_cols[0],
                'title': f'Top Performers by {self.cat_cols[0]}', 'duration': 6
            })
            sections.append({'type': 'insight', 'text': f'Notice how {grp.iloc[0][self.cat_cols[0]]} is dominating the leaderboard.', 'duration': 4})

        # Chart 2: Pie Chart of distribution
        if self.cat_cols and self.num_cols:
            sections.append({
                'type': 'pie', 'data': grp.head(5), 'labels': self.cat_cols[0], 'values': self.num_cols[0],
                'title': f'Market Share of {self.cat_cols[0]}', 'duration': 6
            })

        # Chart 3: Line Chart (Trend)
        if len(self.df) > 1 and self.num_cols:
            sections.append({
                'type': 'line', 'data': self.df.head(15), 'x': self.cat_cols[0] if self.cat_cols else self.df.index.name or 'Index',
                'y': self.num_cols[0], 'title': f'{self.num_cols[0]} Trend Over Time', 'duration': 6
            })

        # Chart 4: Horizontal Bar (Comparison)
        if len(self.num_cols) > 1:
            sections.append({
                'type': 'hbar', 'data': self.df.head(10), 'x': self.cat_cols[0] if self.cat_cols else self.df.index.name or 'Item',
                'y': self.num_cols[1], 'title': f'Secondary Metric: {self.num_cols[1]}', 'duration': 6
            })
            sections.append({'type': 'insight', 'text': f'Comparing this to {self.num_cols[0]} shows some interesting correlations.', 'duration': 4})

        # Chart 5: Scatter (Relationship)
        if len(self.num_cols) >= 2:
            sections.append({
                'type': 'bar', # Scatter is harder to animate, using Bar for variety
                'data': self.df.sample(min(10, len(self.df))), 'x': self.cat_cols[0] if self.cat_cols else self.df.index.name,
                'y': self.num_cols[0], 'title': 'Data Distribution Sample', 'duration': 6
            })

        # Chart 6: Bottom Performers (The "Gaps")
        if self.cat_cols and self.num_cols:
            bottom_grp = self.df.groupby(self.cat_cols[0])[self.num_cols[0]].sum().sort_values().reset_index().head(5)
            sections.append({
                'type': 'bar', 'data': bottom_grp, 'x': self.cat_cols[0], 'y': self.num_cols[0],
                'title': 'Opportunities for Growth', 'duration': 6
            })
            sections.append({'type': 'insight', 'text': 'These areas might need some extra attention next season.', 'duration': 4})

        # Limit to 8 sections for a better experience
        sections = sections[:8]

        # Summary Metrics
        for col in self.num_cols[1:4]:
            metrics.append({
                'label': col,
                'value': f'{self.df[col].sum():,.0f}',
                'delta': f'Avg: {self.df[col].mean():,.0f}',
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
    
    insights = ai_result.get('insights', [])
    charts = ai_result.get('chart_configs', [])
    
    # Narrative interweaving: Insight -> Chart -> Insight -> Chart
    for i in range(max(len(insights), len(charts))):
        if i < len(insights):
            sections.append({'type': 'insight', 'text': insights[i], 'duration': 4})
        if i < len(charts):
            cfg = charts[i]
            try:
                chart_type = cfg.get('type', 'bar')
                x = cfg.get('x_col')
                y = cfg.get('y_col')
                
                if x in df.columns and y in df.columns:
                    sub = df[[x, y]].copy()
                    sub[y] = pd.to_numeric(sub[y], errors='coerce')
                    sub = sub.dropna()
                    
                    if not sub.empty:
                        sections.append({
                            'type': chart_type,
                            'data': sub,
                            'x': x,
                            'y': y,
                            'title': cfg.get('title', 'Chart'),
                            'duration': cfg.get('duration', 6),
                        })
            except Exception:
                continue

    # summary
    kpis = ai_result.get('kpi_metrics', [])
    if kpis:
        sections.append({'type': 'summary', 'metrics': kpis, 'duration': 8})

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