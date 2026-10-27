"""자체 시청 검수 결과 조립: 직접 본 판정(data/review/blind11/verdicts.json) + 오디오 진단(cache/regen/media/diag.json) + 사용자 메모(blind9 labels.json, 곡 구간이 겹치는 행)
-> data/review/blind11/self_check.json, 요약 출력. 판정은 사람이 아니라 내가 프레임/스펙트로그램(experiments/self_check_media.py 그림)을 Read 로 보고 적은 것이다(귀로 듣지는 못함).
verdicts.json: {클립id: {"screen": live|watch|idle|other, "start": ok|preroll|breath|speech|late|..., "end": ok|early|late|speech|..., "why": 근거 1줄, "conf": high|mid|low, "low_why": 사유(low 일 때)}}
사용: python experiments/self_check_build.py [--list]   (--list: 아직 판정이 없는 클립 id)"""
import json, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
BD = ROOT / "data/review/blind11"
SCREENS, STARTS, ENDS, CONFS = {"live", "watch", "idle", "other"}, {"ok", "preroll", "breath", "speech", "late", "soundcheck", "mid"}, {"ok", "early", "late", "speech", "mr", "mid"}, {"high", "mid", "low"}


def memo_rows(slug_dir, s, e):
    L = json.load(open(ROOT / "data/review/blind9/labels.json", encoding="utf8"))
    ov = lambda a, b, c, d: max(0.0, min(b, d) - max(a, c))
    return [dict(lab=r["lab"], memo=r["memo"]) for r in L if r["slug"] == slug_dir and ov(r["ss"], r["se"], s, e) > 0.5 * min(r["se"] - r["ss"], e - s)]


def main():
    D = json.load(open(ROOT / "cache/regen/media/diag.json", encoding="utf8"))
    V = json.load(open(BD / "verdicts.json", encoding="utf8")) if (BD / "verdicts.json").exists() else {}
    if "--list" in sys.argv:
        print([k for k in D if k not in V]); return
    out = {}
    for cid, d in sorted(D.items()):
        v = V.get(cid)
        if not v:
            continue
        assert v["screen"] in SCREENS and v["start"] in STARTS and v["end"] in ENDS and v["conf"] in CONFS and v["why"], (cid, v)
        assert v["conf"] != "low" or v.get("low_why"), cid                    # low 는 사유를 적어야 한다
        j = json.load(open(ROOT / d["mp4"].replace(".mp4", ".json"), encoding="utf8"))
        m = memo_rows(d["mp4"].split("/")[2], j["song_start"], j["song_end"])
        out[cid] = dict(clip=d["clip"], tier=d["tier"], why_tier=d["why"], screen=v["screen"], start=v["start"], end=v["end"], reason=v["why"], conf=v["conf"], low_why=v.get("low_why"),
                        diag={k: d[k] for k in ("song_len", "lead", "trail", "first10", "last10", "speech_lead", "speech_trail", "speech_first10", "speech_last10", "start_db", "end_db", "after_db")},
                        memo=m, memo_vs=v.get("memo_vs"))
    json.dump(out, open(BD / "self_check.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
    c = Counter(v["conf"] for v in out.values())
    print(f"{len(out)}/{len(D)}클립 판정, 확신도 {dict(c)}, 화면 {dict(Counter(v['screen'] for v in out.values()))}, 시작 {dict(Counter(v['start'] for v in out.values()))}, 끝 {dict(Counter(v['end'] for v in out.values()))}")
    print("memo 있는 클립", sum(1 for v in out.values() if v["memo"]), "memo_vs 기록", sum(1 for v in out.values() if v["memo"] and v["memo_vs"]))


if __name__ == "__main__":
    main()
