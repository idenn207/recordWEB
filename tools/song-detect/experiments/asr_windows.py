"""N 신호 평가용 전사 구간 목록: logo_route 신호 표(cache/audit/signals.csv)의 모든 후보 + golden 승인 라이브 중 표에 없는 곡. -> cache/proto_asr/windows.json
gid = '<vno>@<시작초>' (문자열). asr_run.py --set win:cache/proto_asr/windows.json"""
import sys, os, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT); sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
import numpy as np, pandas as pd


def build():
    df = pd.read_csv("cache/audit/signals.csv", keep_default_na=True, na_values=[""], dtype={"vno": str, "tag": str, "multi": str})
    W = [dict(gid=f"{r.vno}@{int(r.start)}", vno=r.vno, base=[float(r.start), float(r.start + r.len)]) for r in df.itertuples()]
    for s in json.load(open("experiments/golden_v4.json", encoding="utf8"))["songs"]:
        a, b = s["frozen"]["s"], s["frozen"]["e"]
        if ((df.vno == s["vid"]) & (np.minimum(df.start + df.len, b) - np.maximum(df.start, a) > 0.5 * (b - a))).any():
            continue
        W.append(dict(gid=f"{s['vid']}@{int(a)}", vno=s["vid"], base=[a, b]))
    seen = set(); W = [w for w in W if not (w["gid"] in seen or seen.add(w["gid"]))]
    ok = [w for w in W if (ROOT / "data/vod" / ("nas" if w["vno"].startswith("20") else "") / f"{w['vno']}.wav").exists()]
    Path("cache/proto_asr/windows.json").write_text(json.dumps(ok), encoding="utf8")
    print(len(df), "표 행 +", len(W) - len(df), "golden 추가 =", len(W), "wav 있음", len(ok), "총 오디오 시간", round(sum(w["base"][1] - w["base"][0] + 120 for w in ok) / 3600, 1), "h")


if __name__ == "__main__":
    build()
