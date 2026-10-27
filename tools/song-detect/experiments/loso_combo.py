"""loso_signals.json 의 특징을 OR 로 묶은 규칙 묶음의 스트리머 단위 LOSO 평가(읽기 전용).
임계값 = 뺀 스트리머 이외 라이브의 극값(라이브 손실 0 이 학습 쪽에서 보장). 기준선 = loso_n 의 streamer 조건(drop/weak, 등록부 끔)과 합침.
사용: python experiments/loso_combo.py [loso_signals.json] [loso.json]"""
import json, sys
from collections import Counter
import numpy as np

S = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "data/review/blind9/audit/loso_signals.json", encoding="utf8"))["items"]
B = {x["key"]: x for x in json.load(open(sys.argv[2] if len(sys.argv) > 2 else "data/review/blind9/audit/loso.json", encoding="utf8"))["items"]}
for i in S:
    b = B.get(i["key"], {})
    i["base_rej"] = str(b.get("streamer", "")).split(":")[0] in ("drop", "weak")        # 기존 규칙(streamer 조건)이 이미 거름
    i["f"]["sing_lo"] = i["f"].get("sing")


RES = []


def loso_rule(rules, items, mult=1.0):
    """rules = [(특징, '>'|'<')]. 반환 {key: 거름 여부} (뺀 스트리머 이외 라이브 극값 기준; mult 로 여유)"""
    out = {}
    for s in {i["name"] for i in items}:
        thr = {}
        for ft, d in rules:
            tr = np.array([i["f"].get(ft) for i in items if i["live"] and i["name"] != s and i["f"].get(ft) is not None], float)
            thr[ft, d] = (tr.max() * mult if d == ">" else tr.min() / mult) if len(tr) >= 10 else None
        for i in items:
            if i["name"] != s:
                continue
            hit = [ft for (ft, d), t in thr.items() if t is not None and i["f"].get(ft) is not None and (i["f"][ft] > t if d == ">" else i["f"][ft] < t)]
            out[i["key"]] = hit
    return out


def run(title, rules, mult=1.0):
    h = loso_rule(rules, S, mult)
    Nl = [i for i in S if i["live"] is False]
    Ll = [i for i in S if i["live"] is True]
    rej = lambda i: i["base_rej"] or bool(h[i["key"]])
    leak = [i for i in Nl if not rej(i)]
    lost = [i for i in Ll if rej(i) and not i["base_rej"]]
    RES.append(dict(title=title, mult=mult, n_leak=len(leak), n_neg=len(Nl), leak=[i["key"] + ":" + str(i["tag"]) for i in leak], lost=[i["key"] for i in lost], n_live=len(Ll)))
    print(f"{title:46} N 남음 {len(leak):2}/{len(Nl)} (유형 {dict(Counter(i['tag'] for i in leak))})  신규 라이브 손실 {len(lost)}/{len(Ll)} {[i['key'][-24:] + str(h[i['key']]) for i in lost]}")
    return leak, lost


if __name__ == "__main__":
    print("기준선(기존 규칙 streamer 조건만):")
    run("기존 규칙만", [])
    for m in (1.0, 1.1):
        print(f"\n--- 극값 여유 x{m}")
        run("+bursts_per_min", [("bursts_per_min", ">")], m)
        run("+sing_std 낮음", [("sing_std", "<")], m)
        run("+bursts +sing_std", [("bursts_per_min", ">"), ("sing_std", "<")], m)
        run("+bursts +sing_std +sp_mid_frac", [("bursts_per_min", ">"), ("sing_std", "<"), ("sp_mid_frac", ">")], m)
        run("+bursts +sing_std +moving_frac", [("bursts_per_min", ">"), ("sing_std", "<"), ("moving_frac", ">")], m)
        run("+bursts +sing_std +moving +static", [("bursts_per_min", ">"), ("sing_std", "<"), ("moving_frac", ">"), ("static_frac", "<")], m)
        run("+bursts +sing_std +ctx_speech_before(<)", [("bursts_per_min", ">"), ("sing_std", "<"), ("ctx_speech_before", "<")], m)
    run("bursts+sing_std (여유 x1.2)", [("bursts_per_min", ">"), ("sing_std", "<")], 1.2)
    json.dump(RES, open("data/review/blind9/audit/loso_combo.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
