```python
import argparse
import sys
import numpy as np
import pandas as pd
from generator import VideoReportGenerator
def _parse_args():
p = argparse.ArgumentParser(description='Analytics Video Report Generator v2')
p.add_argument('--csv', metavar='FILE', default=None, help='Path to CSV')
p.add_argument('--music', metavar='FILE', default=None, help='Music file')
p.add_argument('--volume', type=float, default=0.15, help='Music volume')
p.add_argument('--narrate', action='store_true', help='Enable narration')
p.add_argument('--lang', default='en', help='Narration lang')
p.add_argument('--theme', default='vibrant', help='Visual theme')
p.add_argument('--output', default='analytics_report.mp4',help='Output file')
args, _ = p.parse_known_args()
return args
args = _parse_args()
# SAMPLE DATA (Used if no CSV provided)
sales_data = pd.DataFrame({
'Month': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
'Sales': [45000, 52000, 48000, 61000, 58000, 67000]
})
generator = VideoReportGenerator(theme=args.theme)
generator.generate_report(
config={'sections':[]},
output_file=args.output,
csv_path=args.csv,
music_file=args.music,
music_volume=args.volume,
narrate=args.narrate,
narration_lang=args.lang
)
```