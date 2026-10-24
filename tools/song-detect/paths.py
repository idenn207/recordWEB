"""경로 상수. 원본/정답/라벨은 data/, 다시 만들 수 있는 모든 것은 cache/ (둘 다 .gitignore). 도커에서는 /work/data, /work/cache 로 마운트한다."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA, CACHE = ROOT / "data", ROOT / "cache"


def cache_of(wav, ext):
    """wav 의 탐지 중간 결과(.scores.npy / .vocal.json / .segments.json)는 wav 옆이 아니라 cache/detect/<stem><ext> 에 둔다."""
    return CACHE / "detect" / (Path(wav).stem + ext)
