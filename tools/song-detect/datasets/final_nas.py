"""NAS 10월 방송의 완성본 생성(동시 인코딩 1개, 낮은 우선순위, 전부 이 PC 의 nvenc; NAS 는 원본 읽기만). 카드가 NAS 원본 시각이라 --off 0, 컷 점검용으로 NAS wav 사용.
사용: python datasets/final_nas.py [auto|review|optional ...]   (기본 auto)  ->  out/final, out/final_review, out/final_optional (review/optional 은 ctx20 생략, drop 은 만들지 않음)
  SHARD=k/n 환경변수: 방송 n개 중 k번째 묶음만(0부터, 프로세스를 나눠 동시에 돌릴 때. NAS 읽기가 지연 위주라 동시 실행이 빠르다)"""
import json, os, sys, traceback
from pathlib import Path
R = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(R)); sys.path.insert(0, str(R / "datasets"))
import make_final, nas_ingest as N
K = tuple(int(x) for x in os.environ.get("SHARD", "0/1").split("/"))
assert 0 <= K[0] < K[1]
OUT = dict(auto="out/final", review="out/final_review", optional="out/final_optional")
for t in sys.argv[1:] or ["auto"]:
    for i, r in enumerate(json.load(open(N.IDX, encoding="utf8"))):
        if i % K[1] != K[0]:
            continue
        if not any(json.load(open(c, encoding="utf8"))["tier"] == t for c in (R / "out" / r["slug"] / "cards").glob("*.json")):
            continue
        try:
            make_final.main(r["slug"], N.url_of(r["path"]), r["wav"], 0.0, [t], None, OUT[t], 1, r["streamer"], r["date"], False, t != "auto")
        except Exception:
            traceback.print_exc()
print("끝", flush=True)
