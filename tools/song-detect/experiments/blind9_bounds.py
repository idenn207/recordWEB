"""blind9 경계 평가: 사용자 B/L 메모(HANDOFF 22번, data/review/blind9/labels.json)를 경계 정답으로 구조화하고 현재/후속 경계의 오차를 잰다.
사용:
  python experiments/blind9_bounds.py truth                  # 아래 T 표 -> data/review/blind9/boundary_truth.json 재생성
  python experiments/blind9_bounds.py [소스]                 # 평가. 소스 = 폴더(기본 out/final_review, 하위 json 의 song_start/song_end, 폴더명=slug) 또는 json 파일([{slug, song_start, song_end}])
  python experiments/blind9_bounds.py rules <출력.json> [E1,E2,E3,S1,S2]   # 후보 규칙을 현재 경계에 적용한 제안 경계 -> 위 평가에 그대로 넣는다
  규칙: E1 간주(MR 긴 쉼) 뒤 이어지는 노래로 끝 연장, E2 snap.bridge 의 절벽 직후 에너지 검사를 3초 평균으로(박수/외침 1초 오탐 방지),
        E3 끝 앞 40초 안의 깊은 무음 + 그 뒤 4초가 조용하면 무음 시작에서 끝냄, S1 앞 40초 안의 마지막 MR 정지(>=2초) 뒤로 시작(사운드체크 제외), S2 반주 없는 노래/희박한 MR 앞부분으로 시작 앞당김
오차 = 새 경계 - 정답(초, wav 시간축의 song_start/song_end 기준. 완성본은 시작 앞 최대 2초/끝 뒤 최대 2초 여유가 더 붙는다). 양수: 시작이면 앞이 잘림, 끝이면 뒤가 남음.
평가 대상(eval)은 v3-pad json 만이다(이전 규칙 v2-pad 는 같은 곡의 길이 1초 차이 중복이라 dup_of 로 연결만 한다).
shortcut: 방향 판정은 현재 경계 대비 이동량 1초 이상으로, 숫자 정답은 사용자가 mm:ss 로 말한 값(+-1초)이라 오차 1초 안은 구별 못 한다. 소스는 slug+현재 경계와 겹침(>50%)으로 곡을 찾는다."""
import sys, json, re, inspect
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import snap
from snap import pcm_of, rms_db, HOP
from paths import cache_of

LAB, OUT, DEF = Path("data/review/blind9/labels.json"), Path("data/review/blind9/boundary_truth.json"), Path("out/final_review")
TOL, OKTOL = 1.0, 2.0     # 방향 판정 최소 이동(초), ok 인 곡이 안 움직인 것으로 보는 한도(초)

# 번호 -> (시작, 끝, 시작정답 클립내상대초, 끝정답 클립내상대초, 끝 뒤로 모자란 초, 메모 요약).
# 시작: ok / early(앞에 사운드체크/연습 포함) / late(전주 MR/호흡/허밍이 잘림). 끝: ok / early(곡/MR 이 더 남았는데 잘림) / late(뒤에 멘트 포함) / fade_early(페이드가 너무 빨라 잘린 느낌).
# 상대초 음수 = 클립 시작보다 앞(예: -5 = 전주가 클립 앞에 5초 더 있음). 숫자는 사용자 말(약, 쯤 포함)이라 +-1~3초 불확실.
T = {
    14: ("ok", "ok", None, None, None, ""), 18: ("ok", "early", None, None, 60, "노래가 한 1분 끊긴 듯(사용자 추정)"),
    19: ("ok", "fade_early", None, None, None, ""), 20: ("late", "early", None, None, None, "약 5분 곡이 중간부터 시작, 종료도 더 남음(페이드 너무 빠름)"),
    21: ("late", "early", None, None, None, "20 과 같은 곡(이전 규칙)"), 22: ("ok", "early", None, None, 60, "한 뒤로 1분 정도 노래 끊긴 듯"),
    23: ("ok", "early", None, None, None, "완곡 전 종료"), 24: ("ok", "early", None, None, None, "종료경계 완전히 벗어남(측정 불가)"),
    25: ("ok", "early", None, None, None, "완곡 전 종료"), 26: ("ok", "early", None, None, None, "종료경계 완전히 벗어남(측정 불가)"),
    34: ("ok", "ok", None, None, None, ""), 35: ("ok", "ok", None, None, None, "가수가 후렴부터 MR 끄고 완곡 안 함(경계는 좋음)"), 36: ("ok", "ok", None, None, None, ""),
    44: ("late", "ok", None, None, None, "전주 MR 과 멘트하듯한 부분이 조금 잘림"), 45: ("ok", "ok", None, None, None, ""), 46: ("late", "ok", None, None, None, "들숨/전주 MR 잘림(45 가 더 좋음)"),
    47: ("early", "ok", 26, None, None, "앞은 MR 소리크기 확인, 실제 시작 00:26"),
    48: ("early", "early", 29, None, None, "MR 소리 확인+가사 연습, 실제 시작 00:29, 종료도 완곡 전"), 49: ("early", "early", 29, None, None, "48 과 같은 곡"),
    50: ("late", "ok", None, None, None, "앞부분 조금 잘림"),
    51: ("early", "ok", 6, None, None, "MR 켰다 끄고 다시 부름, 실제 시작 00:06 호흡. 1,2절만 부르고 끝(경계 끝은 정상)"), 52: ("early", "ok", 6, None, None, "51 과 같은 곡"),
    53: ("late", "early", -5, None, None, "전주 MR 약 5초 더 있음, 마지막 '진 세이' 직전 잘림"), 54: ("late", "early", -5, None, None, "53 과 같은 곡"),
    55: ("ok", "ok", None, None, None, ""), 56: ("ok", "ok", None, None, None, ""), 57: ("ok", "ok", None, None, None, ""),
    58: ("late", "ok", None, None, None, "앞에 MR 과 음원이 더 있음"), 59: ("late", "ok", None, None, None, "58 보다 더 잘림"),
    60: ("ok", "late", None, 226, None, "라이브 종료 03:46, 뒤에 멘트까지 남음"), 61: ("ok", "fade_early", None, None, None, "페이드가 1초 정도 더 남았으면(경미)"), 62: ("ok", "fade_early", None, None, None, "61 과 같은 곡"),
    63: ("ok", "early", None, None, None, "완곡 전 종료"), 64: ("ok", "ok", None, None, None, ""),
    65: ("late", "early", None, None, None, "앞 허밍 빠짐, 종료도 완곡 전(마지막이 앞 허밍과 유사)"),
    66: ("ok", "ok", None, None, None, ""), 67: ("ok", "ok", None, None, None, ""), 68: ("ok", "ok", None, None, None, ""), 69: ("ok", "ok", None, None, None, ""),
    70: ("ok", "early", None, None, None, "완곡했으나 MR 끝나기 전 잘림(마지막에 MR 과 함께 멘트)"), 71: ("ok", "early", None, None, None, "70 과 같은 곡"),
    82: ("ok", "early", None, None, None, "완곡했으나 MR 끝나기 전 잘림"), 85: ("ok", "ok", None, None, None, ""), 86: ("ok", "ok", None, None, None, ""), 105: ("ok", "ok", None, None, None, ""),
    111: ("early", "ok", 5, None, None, "앞 5초는 MR 소리 확인, 00:05 부터 실제 시작"),
    112: ("ok", "late", None, 266, None, "완곡 종료 04:26, 뒤가 조금 많이 남음"), 113: ("ok", "late", None, 266, None, "112 와 같은 곡"),
    124: ("ok", "ok", None, None, None, ""), 125: ("ok", "ok", None, None, None, ""), 126: ("ok", "ok", None, None, None, ""),
    127: ("late", "ok", None, None, None, "전주 MR 잘림"), 128: ("late", "ok", None, None, None, "127 과 같은 곡"), 129: ("late", "ok", None, None, None, "전주 MR 조금 잘림"),
    130: ("ok", "fade_early", None, None, None, "fade out 이 완곡 전에 나옴"), 131: ("ok", "ok", None, None, None, ""), 132: ("ok", "ok", None, None, None, ""), 133: ("ok", "ok", None, None, None, ""),
    134: ("late", "ok", None, None, None, "전주 MR 조금 잘림"), 135: ("ok", "ok", None, None, None, "134 의 새 규칙 클립(경계 좋음)"),
    136: ("ok", "fade_early", None, None, None, "완곡 전 fade out, 뒤에 노래가 더 있을 가능성"), 137: ("ok", "fade_early", None, None, None, "136 과 같은 곡"),
    138: ("ok", "ok", None, None, None, ""), 139: ("ok", "ok", None, None, None, ""), 140: ("ok", "ok", None, None, None, ""),
    141: ("ok", "early", None, None, None, "완곡했으나 MR 종료 반주가 남은 채 잘림"), 142: ("ok", "early", None, None, None, "141 과 같은 곡"),
    143: ("ok", "ok", None, None, None, ""), 144: ("late", "ok", None, None, None, "전주 MR 과 노래(멘트하듯)가 많이 잘림"), 145: ("late", "ok", None, None, None, "144 와 같은 곡"),
    33: ("early", "ok", 60, None, None, "N 라벨(BGM 틀어 놓고 멘트), 01:00 쯤부터 MR 라이브 -> 참고용, 평가 제외"),
}


def stem_of(x):
    return x["file"].rsplit(".", 1)[0]


def jload(x):
    return json.load(open(DEF / x["slug"] / (stem_of(x) + ".json"), encoding="utf8"))


def wav_of(slug):
    return f"data/vod/nas/{re.sub(r'^\d+_[^_]+_', '', slug)}.wav"


def build():
    L = json.load(open(LAB, encoding="utf8"))
    J = {i: jload(L[i - 1]) for i in T}
    rows = []
    for i, (st, en, sr, er, miss, note) in sorted(T.items()):
        x, j = L[i - 1], J[i]
        v3 = j["rule"] == "v3-pad"
        dup = None if v3 else next((k for k in T if k != i and J[k]["rule"] == "v3-pad" and L[k - 1]["slug"] == x["slug"]
                                    and abs(J[k]["song_start"] - j["song_start"]) < 8 and abs(J[k]["song_end"] - j["song_end"]) < 8), None)
        rows.append(dict(idx=i, file=x["file"], slug=x["slug"], lab=x["lab"], rule=j["rule"], eval=v3 and x["lab"] != "N", dup_of=dup,
                         vod_start=j["vod_start"], vod_end=j["vod_end"], base_start=j["song_start"], base_end=j["song_end"],
                         start_issue=st, end_issue=en, start_true_rel=sr, end_true_rel=er, missing_sec=miss,
                         start_true_abs=None if sr is None else j["vod_start"] + sr,
                         end_true_abs=j["vod_start"] + er if er is not None else (j["vod_end"] + miss if miss else None),
                         approx=bool(miss) or sr == -5, note=note, memo=x["memo"]))
    live = [r for r in rows if r["lab"] != "N"]
    assert len(live) == 70 and sum(r["eval"] for r in live) == 49 and all(r["dup_of"] for r in live if not r["eval"]), "라이브 70(평가 49, 중복 21) 이어야 한다"
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf8")
    print(f"{OUT}: {len(rows)}행 (평가 {sum(r['eval'] for r in rows)}, 중복 {sum(1 for r in rows if r['dup_of'])})")


def load_src(src):
    p = Path(src)
    if p.is_dir():
        return [dict(slug=f.parent.name, s=j["song_start"], e=j["song_end"], rule=j.get("rule", "")) for f in p.glob("**/*.json")
                if "song_start" in (j := json.load(open(f, encoding="utf8")))]
    return [dict(slug=g["slug"], s=g["song_start"], e=g["song_end"], rule=g.get("rule", "")) for g in json.load(open(p, encoding="utf8"))]


def find(S, r):
    ov = lambda g: min(g["e"], r["base_end"]) - max(g["s"], r["base_start"])
    c = [g for g in S if g["slug"] == r["slug"] and ov(g) > 0.5 * (r["base_end"] - r["base_start"])]
    return max(c, key=lambda g: (ov(g), g["rule"] != "v2-pad"), default=None)


def evaluate(src):
    R = [r for r in json.load(open(OUT, encoding="utf8")) if r["eval"]]
    S = load_src(src)
    num, dr, miss = [], {}, []
    for r in R:
        g = find(S, r)
        if g is None:
            miss.append(r["idx"]); continue
        ds, de = g["s"] - r["base_start"], g["e"] - r["base_end"]
        for side, d, iss, true, base in (("시작", ds, r["start_issue"], r["start_true_abs"], r["base_start"]), ("끝", de, r["end_issue"], r["end_true_abs"], r["base_end"])):
            if true is not None:
                num.append((r["idx"], side, base - true, base + d - true, r["approx"]))
            if iss == "fade_early":
                continue                                           # 페이드 문제는 컷 위치가 아니라 완성본 페이드 규칙의 문제(점수 제외)
            want = {"late": -1, "early": 1} if side == "시작" else {"early": 1, "late": -1}
            ok = abs(d) <= OKTOL if iss == "ok" else d * want[iss] >= TOL
            dr.setdefault((side, iss), []).append((r["idx"], ok, d))
    print(f"소스 {src}: 평가 {len(R)}곡 중 매칭 {len(R) - len(miss)}" + (f", 못 찾음 {miss}" if miss else ""))
    print("숫자 정답 (번호 면 현재오차 -> 새오차, ~ = 대략값)")
    for i, side, e0, e1, ap in num:
        print(f"  #{i} {side} {e0:+6.1f} -> {e1:+6.1f}{' ~' if ap else ''}")
    for tag, sel in (("전체", num), ("대략값 제외", [n for n in num if not n[4]])):
        if sel:
            a0, a1 = np.array([abs(n[2]) for n in sel]), np.array([abs(n[3]) for n in sel])
            print(f"  {tag} {len(sel)}건: 평균|오차| {a0.mean():.1f} -> {a1.mean():.1f}s, 3초 이내 {int((a0 <= 3).sum())} -> {int((a1 <= 3).sum())}건")
    print("방향 일치 (정답 방향으로 1초 이상 이동 / ok 는 2초 안 유지)")
    for k in sorted(dr):
        v = dr[k]
        print(f"  {k[0]} {k[1]:5s}: {sum(o for _, o, _ in v)}/{len(v)}  " + " ".join(f"#{i}{'+' if o else '-'}{d:+.0f}" for i, o, d in v if not o or k[1] != "ok"))
    return num, dr


def with_bridge3():
    """snap._bridge 를 절벽 직후 에너지 검사가 1초 중앙값 대신 3초 평균(dB)인 판으로 바꾼다."""
    src = inspect.getsource(snap._bridge).replace("np.median(rms_db(pcm, c, c + 1)[1])", "np.mean(rms_db(pcm, c, c + 3)[1])")
    ns = dict(snap.__dict__)
    exec(src, ns)
    return ns["_bridge"]


def run_len(a, e, mu=0.85, sp=0.2, gap=2.0, cap=90.0):
    """E1: e 직후부터 (Music>=mu & Speech<sp) 가 gap 초 이하 틈으로 이어지는 길이. e 에서 이미 아니거나 cap 안에 안 끝나면(BGM 가능) 0."""
    i0 = int(e / HOP)
    if not (a[i0, 2] >= mu and a[i0, 1] < sp):
        return 0.0
    last, bad = i0, 0
    for k in range(i0, min(len(a), i0 + int(cap / HOP))):
        if a[k, 2] >= mu and a[k, 1] < sp:
            last, bad = k, 0
        else:
            bad += 1
            if bad * HOP > gap:
                ext = (last - i0) * HOP
                return ext if ext >= 4 else 0.0
    return 0.0


def deep_end(pcm, a, ref, e, look=40.0, depth=30, minlen=0.4, nxt=4.0, nxt_db=12.0):
    """E3: [e-look, e-1.5] 의 마지막 깊은 무음(곡 중앙값-depth dB 미만, Speech<0.3, minlen 초 이상) 뒤 nxt 초 중앙값이 ref-nxt_db 보다 조용하면 그 무음 시작, 아니면 e."""
    ts, db = rms_db(pcm, e - look, e - 1.5)
    q = (db < ref - depth) & (np.array([a[min(int(t / HOP), len(a) - 1), 1] for t in ts]) < 0.3)
    runs, i = [], 0
    while i < len(q):
        j = i
        while j < len(q) and q[j] == q[i]:
            j += 1
        if q[i] and (j - i) * 0.1 >= minlen:
            runs.append((float(ts[i]), float(ts[j - 1]) + 0.1))
        i = j
    if not runs:
        return e
    t0, t1 = runs[-1]
    return t0 if np.median(rms_db(pcm, t1, t1 + nxt)[1]) < ref - nxt_db else e


def vwin(voc, a, t):
    """detect 의 5초 창 (vocal 비율, Speech, Music, 창 시작) - t 가 속한 창."""
    for s0, r in voc:
        n = int((t - s0) // 5)
        if 0 <= n < len(r):
            k = int((s0 + n * 5) / HOP)
            return float(r[n]), float(a[k:k + 10, 1].mean()), float(a[k:k + 10, 2].mean()), s0 + n * 5
    return None


def start_s1(a, voc, s, e, gap=2.0, vmax=0.35, within=40.0, min_left=90.0, lead=1.0):
    """S1: s 뒤 within 초 안의 마지막 Music<0.3 정지(gap 초 이상)가 끝난 곳 - lead 가 새 시작. 정지 앞 5초 창 vocal 평균<vmax(MR 만 나옴)이고 뒤 곡이 min_left 이상일 때만."""
    i0, i1, best, i = int(s / HOP), int(min(e, s + within + 12) / HOP), None, 0
    low = a[i0:i1, 2] < 0.3
    while i < len(low):
        j = i
        while j < len(low) and low[j] == low[i]:
            j += 1
        if low[i] and (j - i) * HOP >= gap and i * HOP <= within and e - (s + j * HOP) >= min_left:
            w = [vwin(voc, a, t) for t in np.arange(s, s + i * HOP, 5.0)]
            w = [x[0] for x in w if x]
            if w and np.mean(w) < vmax:
                best = s + j * HOP - lead
        i = j
    return best if best is not None else s


def start_s2(a, voc, s, vmin=0.6, mumin=0.2, spmax=0.1, maxback=30.0):
    """S2: s 앞으로 5초 창을 거슬러 vocal>=vmin & Music>=mumin & Speech<=spmax 인 창(반주가 희박한 노래)이 이어지는 만큼 시작을 앞당긴다."""
    new, t = s, s - 2.5
    while s - t < maxback:
        w = vwin(voc, a, t)
        if w is None or not (w[0] >= vmin and w[2] >= mumin and w[1] <= spmax):
            break
        new, t = w[3], w[3] - 2.5
    return new


def propose(out, which):
    L = json.load(open(LAB, encoding="utf8"))
    orig, b3, res, seen = snap._bridge, with_bridge3(), [], set()
    for x in L:
        j = jload(x)
        key = (x["slug"], j["song_start"], j["song_end"])
        if j["rule"] != "v3-pad" or key in seen:
            continue
        seen.add(key)
        w = wav_of(x["slug"])
        pcm, a = pcm_of(w), np.load(cache_of(w, ".scores.npy"))
        voc = [(float(k.split("-")[0]), np.array(r)) for k, r in json.load(open(cache_of(w, ".vocal.json"))).items()]
        s, e, why = j["song_start"], j["song_end"], []
        if "E2" in which:
            snap._bridge = b3
            e2 = snap.snap(pcm, a, *j["boundary"]["refine"])[1]
            snap._bridge = orig
            if abs(e2 - e) > 0.05:
                e, why = e2, why + ["E2"]
        if "E1" in which and (d := run_len(a, e)):
            e, why = e + d, why + ["E1"]
        if "E3" in which:
            ref = float(np.median(rms_db(pcm, s, e)[1]))
            if (e3 := deep_end(pcm, a, ref, e)) < e:
                e, why = e3, why + ["E3"]
        if "S1" in which and (s1 := start_s1(a, voc, s, e)) > s:
            s, why = s1, why + ["S1"]
        elif "S2" in which and (s2 := start_s2(a, voc, s)) < s:
            s, why = s2, why + ["S2"]
        res.append(dict(slug=x["slug"], song_start=s, song_end=e, rule="proposal", why=why, idx=L.index(x) + 1))
    Path(out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf8")
    print(f"{out}: {len(res)}곡, 규칙 적용 {sum(bool(g['why']) for g in res)}곡: " + " ".join(f"#{g['idx']}{'+'.join(g['why'])}" for g in res if g["why"]))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["truth"]:
        build()
    elif a[:1] == ["rules"]:
        propose(a[1], (a[2] if len(a) > 2 else "E1,E2,E3,S1,S2").split(","))
    else:
        evaluate(a[0] if a else DEF)
