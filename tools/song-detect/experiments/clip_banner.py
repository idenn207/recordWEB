"""완성본 클립 안에 스트리머의 '클립 금지' 화면 문구가 있는지 훑는다(61방송 재생성 리뷰 C1). 목록만 낸다: 올릴지 뺄지는 사용자가 정한다(정책 결정 전에는 클립을 옮기거나 지우지 않는다).
  python experiments/clip_banner.py [폴더 ...]   기본 out/final out/final_review. 클립마다 7프레임, 흰 글자 마스크(clip_banner_mask.png)와 겹침 0.6 이상이 4프레임 이상이면 표시. 결과는 out/CLIP_BANNER.txt 에도 쓴다.
shortcut: 마스크 하나(nana 10-16 의 '클립 금지', 640x360 화면 오른쪽 가운데 글자)와 위치까지 맞춰 비교한다. 다른 글꼴/위치의 금지 문구는 못 찾으므로 새 문구가 보이면 마스크를 추가한다."""
import subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT = Path(__file__).resolve().parent.parent
REG = (slice(100, 200), slice(350, 640))                         # 640x360 로 줄인 프레임에서 문구가 있는 영역
MASK = np.asarray(Image.open(ROOT / "experiments/clip_banner_mask.png")) > 0
assert MASK.shape == (100, 290) and MASK.sum() > 3000, "마스크 파일 이상"


def frame(mp4, t):
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(mp4), "-frames:v", "1", "-vf", "scale=640:360", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(360, 640, 3)


def hits(mp4):
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)], capture_output=True, text=True, check=True).stdout)
    sc = [float(((frame(mp4, dur * k / 8)[REG].min(axis=2) > 230) & MASK).sum() / MASK.sum()) for k in range(1, 8)]
    return sum(s >= 0.6 for s in sc), max(sc)


if __name__ == "__main__":
    dirs = [Path(a) for a in sys.argv[1:]] or [ROOT / "out/final", ROOT / "out/final_review"]
    found = []
    for d in dirs:
        for mp4 in sorted(d.glob("*/*.mp4")):
            n, mx = hits(mp4)
            if n >= 4:
                found.append((mp4.relative_to(ROOT).as_posix(), n, mx))
    txt = "\n".join(f"{p}  {n}/7 프레임 (최대 겹침 {mx:.2f})" for p, n, mx in found)
    print(f"'클립 금지' 문구가 보이는 클립 {len(found)}개\n{txt}")
    (ROOT / "out/CLIP_BANNER.txt").write_text(f"'클립 금지' 문구가 보이는 완성본 클립 파일 {len(found)}개, auto 는 ctx20 사본 포함 (experiments/clip_banner.py). 올리기 전에 정책을 확인한다.\n{txt}\n", encoding="utf8")
