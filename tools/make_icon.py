# アイコン(仕様書の紙に緑のチェック)を描いて specstatus/assets/ に icon.ico と icon.png を書く。
# 開発用。Pillow が要る(本体は標準ライブラリだけで、できた png/ico を読むだけ)。
# 使い方: python tools/make_icon.py
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "specstatus", "assets")
N = 1024                       # この大きさで描いてから縮める
INK = (43, 58, 85, 255)        # 紙の縁
PAPER = (251, 252, 254, 255)
FOLD = (214, 223, 236, 255)
LINE = (150, 170, 200, 255)
GREEN = (34, 165, 101, 255)
WHITE = (255, 255, 255, 255)


def draw() -> Image.Image:
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, y0, x1, y1, cut, w = 180, 70, 760, 930, 190, 44
    paper = [(x0, y0), (x1 - cut, y0), (x1, y0 + cut), (x1, y1), (x0, y1)]
    d.polygon(paper, fill=PAPER)
    d.line(paper + [paper[0]], fill=INK, width=w, joint="curve")
    d.polygon([(x1 - cut, y0), (x1 - cut, y0 + cut), (x1, y0 + cut)], fill=FOLD)
    d.line([(x1 - cut, y0), (x1 - cut, y0 + cut), (x1, y0 + cut)], fill=INK, width=w, joint="curve")
    for y, right in ((340, 640), (470, 640), (600, 520)):
        d.rounded_rectangle((x0 + 100, y - 26, right, y + 26), radius=26, fill=LINE)
    cx, cy, r = 720, 760, 230
    d.ellipse((cx - r - 40, cy - r - 40, cx + r + 40, cy + r + 40), fill=WHITE)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=GREEN)
    d.line([(cx - 120, cy + 5), (cx - 30, cy + 95), (cx + 125, cy - 85)], fill=WHITE, width=74, joint="curve")
    for (px, py) in ((cx - 120, cy + 5), (cx + 125, cy - 85)):
        d.ellipse((px - 37, py - 37, px + 37, py + 37), fill=WHITE)
    return im


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    big = draw()
    big.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, "icon.png"))
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    big.save(os.path.join(OUT, "icon.ico"), sizes=[(s, s) for s in sizes])
    print("書きました:", os.path.normpath(OUT))


if __name__ == "__main__":
    main()
