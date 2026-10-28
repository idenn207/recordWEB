"""태그별 접촉 시트: python sheet.py <태그|live> <출력.jpg> [곡수=6] -- 곡마다 프레임 0,3,6 (자체 눈 검수용)"""
import json, os, sys, random
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; os.chdir(ROOT)
from PIL import Image, ImageDraw
tag, out = sys.argv[1], sys.argv[2]; n = int(sys.argv[3]) if len(sys.argv) > 3 else 6
rows = json.load(open("cache/proto_visual/manifest.json", encoding="utf8"))
sel = [r for r in rows if (r["live"] == 1 if tag == "live" else r["tag"] == tag)]
random.Random(0).shuffle(sel); sel = sel[:n]
W, H = 266, 150
sh = Image.new("RGB", (W * 3, H * len(sel)))
d = ImageDraw.Draw(sh)
for j, r in enumerate(sel):
    for c, i in enumerate((0, 3, 6)):
        p = Path("cache/proto_visual/frames") / r["key"].replace("/", "__") / f"{i}.jpg"
        if p.exists():
            sh.paste(Image.open(p).resize((W, H)), (c * W, j * H))
    d.text((4, j * H + 2), r["key"][-28:], fill=(255, 255, 0))
sh.save(out, quality=80)
