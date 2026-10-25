"""NAS 10월 방송 중 auto 카드가 있는 것만 make_final 로 완성본 생성(out/final/). 카드가 NAS 원본 시각이라 --off 0, 컷 점검용으로 NAS wav 사용."""
import json, sys, traceback
from pathlib import Path
R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R)); sys.path.insert(0, str(R / "datasets"))
import make_final, nas_ingest as N
for r in json.load(open(N.IDX, encoding="utf8")):
    if not any(json.load(open(c, encoding="utf8"))["tier"] == "auto" for c in (R / "out" / r["slug"] / "cards").glob("*.json")):
        continue
    try:
        make_final.main(r["slug"], N.url_of(r["path"]), r["wav"], 0.0, ["auto"], None, "out/final", 2, r["streamer"], r["date"])
    except Exception:
        traceback.print_exc()
print("끝", flush=True)
