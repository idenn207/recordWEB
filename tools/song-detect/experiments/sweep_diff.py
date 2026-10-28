"""설정 하나가 기준 대비 무엇을 바꿨는지: 메모 숫자 정답/방향 항목의 오차 변화와, 1초 넘게 움직인 곡 경계 목록(방송, 시작초, 시작/끝 이동, 등급·장면).
사용: python experiments/sweep_diff.py '{"snap.E1B_LOUD": 9.0}'   (여러 설정은 JSON 목록)"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep_core as S


def main(cfgs):
    ev = S.Evaluator(8, wide=True)
    base = ev.evaluate({})
    import memo_audit as M
    _, evb = ev.memo(base["_R"])
    for cfg in cfgs:
        r = ev.evaluate(cfg)
        print("== ", cfg, {k: v for k, v in r.items() if not k.startswith("_") and k not in ("gold_flags",)}, "golden:", r["gold_flags"][:6])
        _, evn = ev.memo(r["_R"])
        for a in evb["items"]:
            b = next((x for x in evn["items"] if x["gid"] == a["gid"] and x["side"] == a["side"] and x["kind"] == a["kind"]), None)
            if b and (a.get("err") != b.get("err") or a.get("pass_") != b.get("pass_")):
                print(f"   항목 #{a['gid']} {a['side']} {a['kind']}: " + (f"err {a['err']:+.1f} -> {b['err']:+.1f}" if a["kind"] == "num" else f"move {a['move']:+.1f} -> {b['move']:+.1f} pass {a['pass_']} -> {b['pass_']}"))
        n = 0
        for v in r["_R"]:
            for k, c in r["_R"][v].items():
                o = base["_R"][v][k]
                ds, de, dc = c["song_s"] - o["song_s"], c["song_e"] - o["song_e"], max(abs(c["clip_s"] - o["clip_s"]), abs(c["clip_e"] - o["clip_e"]))
                if max(abs(ds), abs(de)) > 1:
                    n += 1
                    if n <= 25:
                        print(f"   이동 {v} @{k[0]:.0f}: 시작 {ds:+.1f} 끝 {de:+.1f} (원래 {o['song_e'] - o['song_s']:.0f}초)")
        print(f"   1초 넘게 움직인 곡 {n}")
    ev.close()


if __name__ == "__main__":
    c = json.loads(sys.argv[1])
    main(c if isinstance(c, list) else [c])
