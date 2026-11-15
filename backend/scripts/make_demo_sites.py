"""Builds backend/app/demo_sites/files: pages and images for the bundled demo
websites. Copies are edits of web/public/demo/protected.jpg (a drawn scene,
no people). Run from backend/: .venv/Scripts/python scripts/make_demo_sites.py .."""
import math
import random
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

root = Path(sys.argv[1])
src = root / "web/public/demo"
out = root / "backend/app/demo_sites/files"
out.mkdir(parents=True, exist_ok=True)
photo = Image.open(src / "protected.jpg").convert("RGB")
W, H = photo.size

# ---- copies of the protected photo (what an abuser re-posts) ----
w, h = int(W * 0.93), int(H * 0.93)
crop = photo.crop(((W - w) // 2, (H - h) // 2, (W - w) // 2 + w, (H - h) // 2 + h))
crop = ImageEnhance.Color(ImageEnhance.Contrast(crop).enhance(1.08)).enhance(1.3)
crop.save(out / "snap_post.jpg", quality=80)

cap = photo.copy()
d = ImageDraw.Draw(cap)
d.rectangle([0, int(H * 0.91), W, H], fill=(0, 0, 0))
try:
    font = ImageFont.truetype("arial.ttf", int(H * 0.05))
except OSError:
    font = ImageFont.load_default()
d.text((W // 2, int(H * 0.955)), "look who it is", fill=(255, 255, 255), font=font, anchor="mm")
cap = cap.resize((W // 2, H // 2))
cap.save(out / "forum_upload.jpg", quality=55)

shutil.copy(src / "protected.jpg", out / "dump_exact.jpg")  # byte-identical repost

# ---- unrelated images ----
for n in ("city", "forest", "ocean"):
    shutil.copy(src / f"{n}.jpg", out / f"{n}.jpg")


def avatar(seed, path):
    random.seed(seed)
    img = Image.new("RGB", (160, 160))
    d = ImageDraw.Draw(img)
    a = (random.randint(40, 200), random.randint(40, 200), random.randint(40, 200))
    b = (random.randint(40, 200), random.randint(40, 200), random.randint(40, 200))
    for y in range(160):
        t = y / 160
        d.line([(0, y), (160, y)], fill=tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)))
    for _ in range(6):
        x, y, r = random.randint(0, 160), random.randint(0, 160), random.randint(10, 40)
        d.ellipse([x - r, y - r, x + r, y + r], outline=(255, 255, 255), width=3)
    img.save(path, quality=85)


avatar(11, out / "avatar_a.jpg")
avatar(12, out / "avatar_b.jpg")


def morning_lake(path):
    """A DIFFERENT lake photo: same subject, not the same image."""
    random.seed(7)
    img = Image.new("RGB", (720, 540))
    d = ImageDraw.Draw(img)
    for y in range(540):
        t = y / 540
        d.line([(0, y), (720, y)], fill=(int(150 + 90 * t), int(200 + 30 * t), int(240 - 20 * t)))
    d.ellipse([120, 90, 200, 170], fill=(255, 250, 220))
    pts = [(0, 540)] + [(x, 250 - 90 * abs(math.sin(x / 140)) - random.randint(0, 20)) for x in range(0, 740, 20)] + [(720, 540)]
    d.polygon(pts, fill=(70, 110, 90))
    d.rectangle([0, 330, 720, 540], fill=(60, 120, 160))
    for _ in range(30):
        y = random.randint(340, 530)
        x = random.randint(0, 720)
        d.line([(x - 40, y), (x + 40, y)], fill=(200, 230, 245), width=2)
    img.save(path, quality=85)


morning_lake(out / "blog_lake.jpg")

CSS = ("body{font-family:sans-serif;max-width:680px;margin:2rem auto;background:#fafafa;color:#222}"
       "img{max-width:100%;display:block;margin:1rem 0;border-radius:8px}.small{width:64px}")

pages = {
    "snapgram_post.html": f"""<!doctype html><html><head><meta charset="utf-8">
<title>@night_owl_99 on Snapgram</title>
<meta property="og:image" content="/media/snap_post.jpg"><style>{CSS}</style></head><body>
<header><img class="small" src="/media/avatar_a.jpg" alt=""> <b>night_owl_99</b></header>
<img src="/media/snap_post.jpg" alt="post"><p>throwback &#128064;</p>
<h4>Suggested for you</h4><img src="/media/forest.jpg" alt=""><img src="/media/city.jpg" alt="">
</body></html>""",
    "forum_thread.html": f"""<!doctype html><html><head><meta charset="utf-8">
<title>Thread 48213 - ChatForum</title><style>{CSS}</style></head><body>
<h1>random pics thread</h1>
<p><img class="small" src="/img/avatar_b.jpg" alt=""> anon1: first</p><img src="/img/ocean.jpg" alt="">
<p><img class="small" src="/img/avatar_a.jpg" alt=""> anon2:</p><img src="/img/forum_upload.jpg" alt="">
<p>anon3: lol</p><img src="/img/city.jpg" alt="">
</body></html>""",
    "blog_post.html": f"""<!doctype html><html><head><meta charset="utf-8">
<title>Lakes of the North - Travel Blog</title><style>{CSS}</style></head><body>
<h1>Lakes of the North</h1><p>Our favourite mornings by the water.</p>
<img src="/photos/blog_lake.jpg" alt=""><img src="/photos/forest.jpg" alt="">
<img src="/photos/ocean.jpg" alt=""></body></html>""",
}
for name, html in pages.items():
    (out / name).write_text(html, encoding="utf-8")
print("built", out)
