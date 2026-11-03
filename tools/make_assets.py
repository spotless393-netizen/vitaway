# -*- coding: utf-8 -*-
"""Bot uchun animatsiyalar (MP4) va avatar yasaydi. Kerak: Pillow, numpy, ffmpeg."""
import math, os, random, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(os.path.dirname(HERE), "assets")
FONT = os.environ.get("VW_FONT", "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf")
N = 1024            # ichki o'lcham (2x), chiqish 512
FPS = 30
BG = (244, 249, 253)
INK = (23, 50, 77)
BLUE = (30, 155, 239); BLUE_D = (11, 111, 192); ORANGE = (255, 138, 0)
COLS = [(30, 155, 239), (242, 195, 17), (155, 197, 61), (255, 138, 0), (255, 255, 255)]

LOGO = Image.open(os.path.join(A, "logo.png")).convert("RGBA")
PACKS = {k: Image.open(os.path.join(A, f"pack_{k}.png")).convert("RGBA") for k in ("neuro", "immuno", "osteo", "antihelmo")}
_fonts = {}
def font(sz):
    if sz not in _fonts: _fonts[sz] = ImageFont.truetype(FONT, sz)
    return _fonts[sz]

def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def prog(t, a, b): return clamp((t - a) / (b - a))
def out_cubic(x): return 1 - (1 - x) ** 3
def out_back(x, s=1.70158): x -= 1; return x * x * ((s + 1) * x + s) + 1
def out_elastic(x):
    if x in (0, 1): return x
    return 2 ** (-10 * x) * math.sin((x * 10 - .75) * (2 * math.pi) / 3) + 1

BLOBS = [((0.02, 0.04), 0.30, (169, 210, 240)), ((0.50, -0.04), 0.24, (242, 195, 17)), ((1.0, 0.06), 0.30, (181, 203, 37)),
         ((0.02, 1.0), 0.32, (30, 155, 239)), ((0.52, 1.04), 0.22, (243, 226, 169)), ((1.0, 0.98), 0.30, (255, 138, 0))]

def background(t, alpha=0.55):
    im = Image.new("RGBA", (N, N), BG + (255,))
    lay = Image.new("RGBA", (N, N), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    for i, ((x, y), r, c) in enumerate(BLOBS):
        R = r * N; X = x * N + math.sin(t * 1.3 + i) * 14; Y = y * N + math.cos(t * 1.1 + i * 2) * 14
        pts = []
        for k in range(64):
            a = k / 64 * 2 * math.pi
            rr = R * (1 + .06 * math.sin(a * 3 + t * 2 + i))
            pts.append((X + math.cos(a) * rr, Y + math.sin(a) * rr))
        d.polygon(pts, fill=c + (int(255 * alpha),))
    im.alpha_composite(lay)
    return im

def paste(base, img, cx, cy, w=None, h=None, rot=0, alpha=1.0, shadow=False):
    if w is None and h is None: w = img.width
    if h is None: h = w * img.height / img.width
    if w is None: w = h * img.width / img.height
    if w < 2 or h < 2 or alpha <= 0: return
    im = img.resize((max(1, int(w)), max(1, int(h))), Image.LANCZOS)
    if rot: im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 1:
        a = im.getchannel("A").point(lambda v: int(v * alpha)); im.putalpha(a)
    if shadow:
        sh = Image.new("RGBA", im.size, (11, 60, 110, 0)); sh.putalpha(im.getchannel("A").point(lambda v: int(v * .28)))
        sh = sh.filter(ImageFilter.GaussianBlur(14))
        base.alpha_composite(sh, (int(cx - im.width / 2), int(cy - im.height / 2 + 16)))
    base.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))

def text(base, s, cx, cy, size, fill=INK, scale=1.0, alpha=1.0, stroke=10, stroke_fill=(255, 255, 255)):
    if scale <= 0.01 or alpha <= 0: return
    f = font(max(8, int(size * scale)))
    lay = Image.new("RGBA", (N, N), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    d.text((cx, cy), s, font=f, fill=fill + (255,), anchor="mm", stroke_width=int(stroke * scale), stroke_fill=stroke_fill + (255,))
    if alpha < 1: lay.putalpha(lay.getchannel("A").point(lambda v: int(v * alpha)))
    base.alpha_composite(lay)

def rich(base, parts, cx, cy, size, scale=1.0, alpha=1.0):
    """Bir qatorda turli rangli bo'laklar: [(matn, rang), ...]"""
    f = font(max(8, int(size * scale)))
    widths = [f.getlength(p) for p, _ in parts]; x = cx - sum(widths) / 2
    for (p, c), w in zip(parts, widths):
        text(base, p, x + w / 2, cy, size, c, scale, alpha); x += w

class Confetti:
    def __init__(self, seed, x, y, n=140, t0=0.0, spread=1.0):
        r = random.Random(seed); self.t0 = t0; self.p = []
        for i in range(n):
            a = r.uniform(-math.pi, 0); v = r.uniform(500, 1300) * spread
            self.p.append((x, y, math.cos(a) * v, math.sin(a) * v - 200, r.uniform(0, 6), r.uniform(4, 9), COLS[i % 4], r.uniform(14, 26)))
    def draw(self, base, t):
        dt = t - self.t0
        if dt < 0 or dt > 3: return
        lay = Image.new("RGBA", (N, N), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        for x, y, vx, vy, a0, spin, c, s in self.p:
            px = x + vx * dt * 0.9; py = y + vy * dt + 900 * dt * dt
            if py > N + 40: continue
            ang = a0 + spin * dt; w, h = s, s * .55
            pts = [(px + math.cos(ang) * dx - math.sin(ang) * dy, py + math.sin(ang) * dx + math.cos(ang) * dy)
                   for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
            d.polygon(pts, fill=c + (int(255 * clamp(1.6 - dt / 1.6)),))
        base.alpha_composite(lay)

def basket(base, cx, cy, w=300, squash=0.0):
    h = w * .62; lay = Image.new("RGBA", (N, N), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    sx, sy = 1 + squash * .1, 1 - squash * .1
    W, H = w * sx, h * sy
    d.ellipse((cx - W * .5, cy + H * .5, cx + W * .5, cy + H * .72), fill=(11, 60, 110, 40))
    d.arc((cx - W * .37, cy - H * .35 - W * .37, cx + W * .37, cy - H * .35 + W * .37), 200, 340, fill=BLUE_D + (255,), width=int(w * .055))
    top = cy - H * .35
    d.polygon([(cx - W / 2, top), (cx + W / 2, top), (cx + W * .4, cy + H * .5), (cx - W * .4, cy + H * .5)], fill=BLUE + (255,))
    for i in range(-5, 6):
        d.line([(cx + i * W / 10, top), (cx + i * W / 10 + H * .25, cy + H * .5)], fill=(255, 255, 255, 45), width=4)
    d.rounded_rectangle((cx - W / 2 - 6, top - H * .07, cx + W / 2 + 6, top + H * .07), radius=10, fill=BLUE_D + (255,))
    d.rounded_rectangle((cx - W * .44, cy - H * .1, cx + W * .44, cy + H * .18), radius=14, fill=(255, 255, 255, 255))
    base.alpha_composite(lay)
    paste(base, LOGO, cx, cy + H * .04, w=W * .62)

def render(name, dur, frame_fn):
    tmp = tempfile.mkdtemp()
    n = int(dur * FPS)
    for i in range(n):
        t = i / FPS
        im = frame_fn(t).convert("RGB").resize((512, 512), Image.LANCZOS)
        im.save(os.path.join(tmp, f"{i:04d}.png"))
    out = os.path.join(A, f"{name}.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(tmp, "%04d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "24",
                    "-movflags", "+faststart", "-an", out], check=True)
    shutil.rmtree(tmp)
    print(name, os.path.getsize(out) // 1024, "KB")

# ---------------------------------------------------------------- 1) Xush kelibsiz
def f_welcome(t):
    im = background(t)
    s = out_back(prog(t, 0.05, 0.75))
    paste(im, LOGO, 512, 250 + math.sin(t * 2) * 6, w=640 * s)
    keys = ["neuro", "immuno", "osteo", "antihelmo"]
    for i, k in enumerate(keys):
        p = out_back(prog(t, 0.6 + i * 0.14, 1.25 + i * 0.14), 1.3)
        x = 200 + i * 208; y = 1250 - (1250 - 640) * p + math.sin(t * 2.4 + i) * 8 * p
        paste(im, PACKS[k], x, y, h=380, rot=(-6 if i % 2 else 6) * (1 - p) + math.sin(t * 1.8 + i) * 2, shadow=True)
    q = out_back(prog(t, 1.75, 2.3))
    text(im, "Xush kelibsiz!", 512, 930, 92, BLUE_D, scale=q)
    return im

# ---------------------------------------------------------------- 2) 20 kun
CONF20 = Confetti(7, 512, 520, 160, t0=1.65)
def f_day20(t):
    im = background(t)
    paste(im, LOGO, 512, 120, w=340 * out_cubic(prog(t, 0, .5)))
    s = out_back(prog(t, 0.05, 0.6)) * (1 + 0.08 * math.sin(clamp((t - 1.6) / .35) * math.pi))
    R = 280 * s; cx, cy = 512, 520
    if R > 4:
        lay = Image.new("RGBA", (N, N), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        rot = t * 90
        for i, c in enumerate([(155, 197, 61), (242, 195, 17), (255, 138, 0), (30, 155, 239)]):
            d.pieslice((cx - R, cy - R, cx + R, cy + R), rot + i * 90, rot + i * 90 + 90, fill=c + (255,))
        r2 = R * .8
        d.ellipse((cx - r2, cy - r2, cx + r2, cy + r2), fill=(255, 255, 255, 255))
        im.alpha_composite(lay)
        num = max(1, int(round(1 + 19 * out_cubic(prog(t, 0.35, 1.55)))))
        text(im, str(num), cx, cy - 30 * s, 250, BLUE, scale=s, stroke=0)
        text(im, "KUN", cx, cy + 120 * s, 64, (90, 118, 144), scale=s, stroke=0)
    CONF20.draw(im, t)
    q = out_back(prog(t, 1.75, 2.3))
    text(im, "20 kun to'ldi!", 512, 900, 96, BLUE_D, scale=q)
    return im

# ---------------------------------------------------------------- 3) O'yin taklifi
DROPS = [("antihelmo", 0.35, 330), ("osteo", 1.05, 640), ("neuro", 1.75, 420), ("immuno", 2.45, 560)]
def f_offer(t):
    im = background(t, .45)
    # savatcha harakati: navbatdagi tushayotgan mahsulot tagiga boradi
    bx = 512; by = 850
    path = [(0, 512)] + [(tt + 0.55, x) for _, tt, x in DROPS] + [(9, 512)]
    for (t1, x1), (t2, x2) in zip(path, path[1:]):
        if t1 <= t <= t2:
            bx = x1 + (x2 - x1) * out_cubic(clamp((t - t1) / max(.01, (t2 - t1) * .8))); break
    squash = 0
    for k, t0, x in DROPS:
        dt = t - t0
        if 0 <= dt < 0.6:
            y = 380 + (800 - 380) * (dt / 0.6) ** 1.6
            paste(im, PACKS[k], x, y, h=230, rot=math.sin(dt * 6) * 4, alpha=clamp(dt / .12), shadow=True)
        if 0.6 <= dt < 0.75: squash = 1 - (dt - .6) / .15
        if 0.6 <= dt < 1.4:
            a = 1 - (dt - .6) / .8
            text(im, "+1", x, 700 - (dt - .6) * 160, 70, BLUE, alpha=a)
            lay = Image.new("RGBA", (N, N), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
            for j in range(10):
                ang = j / 10 * 2 * math.pi; r = 40 + (dt - .6) * 260
                px, py = x + math.cos(ang) * r, 780 + math.sin(ang) * r * .6
                d.ellipse((px - 9, py - 9, px + 9, py + 9), fill=COLS[j % 4] + (int(255 * a),))
            im.alpha_composite(lay)
    basket(im, bx, by, 300, squash)
    q = out_back(prog(t, 0.0, 0.55))
    rich(im, [("20% ", ORANGE), ("gacha", INK)], 512, 120, 104, scale=q)
    text(im, "chegirma yutib oling!", 512, 225, 62, INK, scale=out_back(prog(t, 0.2, 0.7)))
    return im

# ---------------------------------------------------------------- 4) Yutuq
CONFW = [Confetti(11, 250, 600, 90, 0.5), Confetti(12, 774, 600, 90, 0.7), Confetti(13, 512, 450, 120, 1.0)]
def star(d, cx, cy, R, r, rot, fill):
    pts = []
    for i in range(10):
        a = rot + i * math.pi / 5 - math.pi / 2; rr = R if i % 2 == 0 else r
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    d.polygon(pts, fill=fill)
def f_win(t):
    im = background(t, .4)
    lay = Image.new("RGBA", (N, N), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    cx, cy = 512, 470
    ra = out_cubic(prog(t, 0.1, 0.7))
    for i in range(16):
        a0 = t * .5 + i * math.pi / 8
        d.polygon([(cx, cy), (cx + math.cos(a0) * 900, cy + math.sin(a0) * 900),
                   (cx + math.cos(a0 + .12) * 900, cy + math.sin(a0 + .12) * 900)], fill=(255, 214, 102, int(110 * ra)))
    s = out_elastic(prog(t, 0.15, 1.1))
    if s > 0.02:
        star(d, cx, cy + 8, 300 * s, 140 * s, math.sin(t * 2) * .06, (230, 150, 0, 255))
        star(d, cx, cy, 290 * s, 132 * s, math.sin(t * 2) * .06, (255, 196, 30, 255))
    im.alpha_composite(lay)
    if s > 0.02: text(im, "%", cx, cy + 6, 190, (255, 255, 255), scale=s, stroke=12, stroke_fill=(230, 150, 0))
    for c in CONFW: c.draw(im, t)
    q = out_back(prog(t, 0.9, 1.4))
    text(im, "Tabriklaymiz!", 512, 820, 104, BLUE_D, scale=q)
    paste(im, LOGO, 512, 950, w=260 * out_cubic(prog(t, 1.2, 1.7)))
    return im

def avatar():
    im = background(0.0, .9).resize((640, 640), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.ellipse((60, 60, 580, 580), fill=(255, 255, 255, 255))
    paste(im, LOGO, 320, 320, w=420)
    im.convert("RGB").save(os.path.join(A, "avatar.png"))
    print("avatar ok")

if __name__ == "__main__":
    which = sys.argv[1:] or ["avatar", "welcome", "day20", "offer", "win"]
    if "avatar" in which: avatar()
    if "welcome" in which: render("welcome", 3.4, f_welcome)
    if "day20" in which: render("day20", 3.4, f_day20)
    if "offer" in which: render("offer", 3.6, f_offer)
    if "win" in which: render("win", 3.4, f_win)
