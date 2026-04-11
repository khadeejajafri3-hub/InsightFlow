```python
from __future__ import annotations
import json
import os
import re
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
# GEMINI API Setup
GEMINI_AVAILABLE = False
try:
import google.generativeai as genai
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
genai.configure(api_key=api_key)
GEMINI_AVAILABLE = True
except Exception as e:
GEMINI_AVAILABLE = False
```

```python
def _gemini_analyse(df: pd.DataFrame) -> dict | None:
if not GEMINI_AVAILABLE: return None
try:
preview = df.head(30).to_csv(index=False)
stats = df.describe(include='all').to_string()
prompt = f"Data Analytics Task. Preview: {preview}\nStats: {stats}\nReturn JSON
with title, insights, chart_configs."
model = genai.GenerativeModel("gemini-1.5-flash")
response = model.generate_content(prompt)
return json.loads(response.text.strip().replace("```json", "").replace("```", ""))
except: return None
class HeuristicAnalyser:
def __init__(self, df: pd.DataFrame):
self.df = df
self.num_cols = df.select_dtypes(include='number').columns.tolist()
self.cat_cols = df.select_dtypes(include='object').columns.tolist()
def analyse(self):
sections = []
if self.cat_cols and self.num_cols:
grp = self.df.groupby(self.cat_cols[0])[self.num_cols[0]].sum().reset_index()
sections.append({'type': 'bar', 'data': grp, 'x': self.cat_cols[0], 'y': self.num_cols[0],
'title': f'{self.num_cols[0]} by {self.cat_cols[0]}'})
return {'sections': sections, 'summary_metrics': []}
```