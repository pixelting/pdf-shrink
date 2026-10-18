"""Draws the app icon (a page being squeezed) as packaging/icon.png. Run: python packaging/make_icon.py"""
import os
from PIL import Image, ImageDraw

S = 1024
here = os.path.dirname(os.path.abspath(__file__))

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# rounded-square background with a vertical gradient
grad = Image.new("RGBA", (S, S))
gd = ImageDraw.Draw(grad)
for y in range(S):
    t = y / S
    gd.line([(0, y), (S, y)], fill=(int(46 + 30 * t), int(112 + 40 * t), int(235 - 35 * t), 255))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=210, fill=255)
img.paste(grad, (0, 0), mask)

# the page, with a folded corner
px0, py0, px1, py1 = 300, 190, 724, 834
fold = 120
d.polygon([(px0, py0), (px1 - fold, py0), (px1, py0 + fold), (px1, py1), (px0, py1)], fill=(255, 255, 255, 255))
d.polygon([(px1 - fold, py0), (px1 - fold, py0 + fold), (px1, py0 + fold)], fill=(205, 220, 245, 255))
for i, w in enumerate([300, 300, 220]):
    y = 420 + i * 80
    d.rounded_rectangle([px0 + 52, y, px0 + 52 + w - 52, y + 28], radius=14, fill=(150, 175, 215, 255))

# two arrows squeezing in from the sides
ac = (255, 255, 255, 255)
d.polygon([(268, 512), (150, 440), (150, 490), (100, 490), (100, 534), (150, 534), (150, 584)], fill=ac)
d.polygon([(S - 268, 512), (S - 150, 440), (S - 150, 490), (S - 100, 490), (S - 100, 534), (S - 150, 534), (S - 150, 584)], fill=ac)

img.save(os.path.join(here, "icon.png"))
print("wrote", os.path.join(here, "icon.png"))
