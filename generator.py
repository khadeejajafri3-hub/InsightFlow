```python
from PIL import Image, ImageDraw, ImageFont
import numpy as np
W, H = 1920, 1080 # Full HD Resolution
def _load_font(size, bold=False):
# Cross-platform font loading
paths = ['/Windows/Fonts/arial.ttf',
'/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf']
for p in paths:
if os.path.exists(p): return ImageFont.truetype(p, size)
return ImageFont.load_default()
class SlideComposer:
def __init__(self, theme):
self.t = theme
def title_slide(self, title, subtitle, progress=1.0):
img = Image.new('RGB', (W, H), self.t['bg_bottom'])
draw = ImageDraw.Draw(img)
font = _load_font(100, True)
draw.text((W/2, H/2), title, font=font, fill=self.t['text_primary'], anchor="mm")
return img
```

```python
import matplotlib.pyplot as plt
import io
class ChartBuilder:
def __init__(self, theme):
self.t = theme
def bar(self, data, x, y):
plt.style.use(self.t.get('mpl_style', 'dark_background'))
fig, ax = plt.subplots(figsize=(16, 8))
ax.bar(data[x], data[y], color=self.t['chart_colors'][0])
# Convert Matplotlib figure to PIL Image
buf = io.BytesIO()
fig.savefig(buf, format='png', transparent=True)
plt.close(fig)
return Image.open(buf)
```

```python
from moviepy.editor import VideoClip, concatenate_videoclips
class VideoReportGenerator:
def generate_report(self, config, output_file='report.mp4', csv_path=None):
if csv_path:
# Auto-extract logic
pass
clips = []
for section in config['sections']:
# Create a VideoClip from our SlideComposer frames
def make_frame(t):
# Logic to return a numpy array of a frame
return np.array(frame)
clips.append(VideoClip(make_frame, duration=5))
final = concatenate_videoclips(clips)
final.write_videofile(output_file, fps=30)
```

```python
from gtts import gTTS
def _generate_narration(text, path):
tts = gTTS(text=text, lang='en')
tts.save(path)
# Inside VideoReportGenerator
# audio = AudioFileClip("uploads/narr.mp3")
# clip = clip.set_audio(audio)