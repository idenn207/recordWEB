"""boundary 트랙 제안 규칙 모음(시험용, snap.py 에 연결 안 됨). 모두 prop(pcm, a, voc, s, e, s0, e0) -> (s, e) 를 돌려주는 팩토리.
 s,e = 기존 snap 결과, s0,e0 = snap 입력(refine 경계). 점수 a 열 = Singing, Speech, Music (0.5초). dB 는 cache/proto_boundary/db 트랙(0.1초 프레임).
시작: s3(마지막 깊은 무음 끝), s3e(g1 엔벨로프판), breath(호흡 보존), s4(무음 뒤 +dB 단차)  끝: e4(조용한 꼬리), e5(에너지 미확인 끝)  합성: seq(...)
shortcut: 임계값은 모두 격자 탐색 대상이며 표본(메모 곡 약 25개 + 승인 113곡) 안에서만 검증했다."""
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
import numpy as np
from snap import rms_db, HOP

DB = ROOT / "cache/proto_boundary/db"
_T = {}


def dbt(pcm):
    """pcm(memmap) 전체의 0.1초 프레임 dBFS 트랙. 트랙 파일이 없으면 만들지 않고 None."""
    k = getattr(pcm, "filename", None)
    if k not in _T:
        f = DB / (Path(str(k)).stem + ".npy")
        _T[k] = np.load(f) if f.exists() else None
    return _T[k]


def ref_of(pcm, s, e):
    d = dbt(pcm)
    return float(np.median(d[int(s / 0.1):int(e / 0.1)])) if d is not None else float(np.median(rms_db(pcm, s, e)[1]))


def runs(m):
    """bool 배열의 (값, 시작, 끝) 연속 구간."""
    out, i = [], 0
    while i < len(m):
        j = i
        while j < len(m) and m[j] == m[i]:
            j += 1
        out.append((bool(m[i]), i, j))
        i = j
    return out


def sp_of(a, t0, t1):
    return a[int(t0 / HOP):max(int(t1 / HOP), int(t0 / HOP) + 1), 1]


# ---------------- 시작 ----------------
def s3(back=30.0, thr=-50.0, rel=None, minlen=0.5, spf=0.4, spth=0.5, mu=0.0, skip_moved=True, minmove=1.0, spfloor=False, extmu=None, name="s3"):
    """S3: 시작 앞 back 초 안의 마지막 깊은 무음(절대 thr dB 미만, rel 이 있으면 곡 중앙값-rel dB 미만, minlen 초 이상)의 끝으로 시작을 당긴다.
    가드: 그 사이 Speech>spth 프레임 비율 >= spf 이면 안 함, 사이 Music 평균 < mu 이면 안 함, S1 이 시작을 뒤로 민 곡(s-s0>1)은 건너뜀(skip_moved),
    spfloor: 사이에 2.5초 이상 이어진 말(Speech>=0.5)이 있으면 그 끝+0.3초를 하한으로."""
    def prop(pcm, a, voc, s, e, s0, e0):
        d = dbt(pcm)
        if d is None or (skip_moved and s - s0 > 1.0):
            return s, e
        i1, i0 = int(s / 0.1), max(0, int((s - back) / 0.1))
        th = thr if rel is None else ref_of(pcm, s, e) - rel
        r = [x for x in runs(d[i0:i1] < th) if x[0] and (x[2] - x[1]) * 0.1 >= minlen]
        if not r:
            return s, e
        cand = (i0 + r[-1][2]) * 0.1
        if s - cand < minmove:
            return s, e
        seg = a[int(cand / HOP):int(s / HOP)]
        if len(seg) and ((seg[:, 1] > spth).mean() >= spf or seg[:, 2].mean() < mu or (extmu is not None and (seg[:, 0] + seg[:, 2]).mean() < extmu)):
            return s, e
        if spfloor:
            sp = sp_of(a, cand, s) >= 0.5
            rr = [x for x in runs(sp) if x[0] and (x[2] - x[1]) * HOP >= 2.5]
            if rr:
                cand = max(cand, cand + rr[-1][2] * HOP + 0.3)
                if s - cand < minmove:
                    return s, e
        return cand, e
    prop.__name__ = name
    return prop


def s3e(back=60.0, deep=35.0, sp_run=2.5, mu=0.5, minmove=3.0, minsil=1.0, name="s3e"):
    """g1_envelope_start 이식: 뒤에서 앞으로 가며 말(Speech>=0.5 가 sp_run 초 연속)이면 멈추고, 곡 중앙값-deep dB 미만 무음이 minsil 초 이상이면 그 끝. 사이 Music 평균>=mu, 이동>=minmove."""
    def prop(pcm, a, voc, s, e, s0, e0):
        d = dbt(pcm)
        if d is None or s - s0 > 1.0:
            return s, e
        ref = ref_of(pcm, s, e)
        i1, i0 = int(s / 0.1), max(0, int((s - back) / 0.1))
        ts = np.arange(i0, i1) * 0.1
        sp = a[np.minimum((ts / HOP).astype(int), len(a) - 1), 1]
        dp = d[i0:i1] < ref - deep
        spn = int(sp_run / 0.1)
        t0 = None
        for i in range(len(ts) - 1, -1, -1):
            if sp[i] >= 0.5 and (sp[max(0, i - spn + 1):i + 1] >= 0.5).all():
                break
            if dp[i]:
                j = i
                while j >= 0 and dp[j]:
                    j -= 1
                if i - j >= minsil / 0.1:
                    t0 = float(ts[i]) + 0.1
                    break
        if t0 is None or s - t0 < minmove:
            return s, e
        seg = a[int(t0 / HOP):int(s / HOP)]
        return (t0, e) if len(seg) and seg[:, 2].mean() >= mu else (s, e)
    prop.__name__ = name
    return prop


def breath(win=4.0, quiet_db=-60.0, qmin=0.5, lo=-62.0, hi_rel=25.0, smin=0.3, smax=1.5, lead=0.2, skip_moved=False, name="breath"):
    """호흡 보존: s 앞 win 초 안에서 '깊은 무음(qmin 초 이상, quiet_db 미만)' 바로 앞의 단발 저레벨 소리(절대 lo dB 초과 & 곡 중앙값-hi_rel dB 미만, smin~smax 초)를 찾아 그 시작 - lead 로 당긴다.
    S1 이 시작을 밀어 놓은 곡도 대상(호흡은 새 시작의 앞이므로)이 되지만 skip_moved 로 끌 수 있다."""
    def prop(pcm, a, voc, s, e, s0, e0):
        d = dbt(pcm)
        if d is None or (skip_moved and s - s0 > 1.0):
            return s, e
        ref = ref_of(pcm, s, e)
        i1, i0 = int(s / 0.1), max(0, int((s - win) / 0.1))
        x = d[i0:i1]
        if len(x) < 10:
            return s, e
        R = runs(x < quiet_db)
        sil = [r for r in R if r[0] and (r[2] - r[1]) * 0.1 >= qmin]
        if not sil:
            return s, e
        k0 = sil[-1][1] if sil[-1][2] >= len(x) - 5 else sil[-1][1]     # s 직전의 마지막 무음 시작
        # 그 무음 바로 앞 소리 구간(무음이 아닌 연속)
        j = k0
        while j > 0 and x[j - 1] >= quiet_db:
            j -= 1
        seg = x[j:k0]
        L = len(seg) * 0.1
        if L < smin or L > smax or seg.max() > ref - hi_rel or seg.max() < lo:
            return s, e
        return (i0 + j) * 0.1 - lead, e
    prop.__name__ = name
    return prop


def s4(within=90.0, gap=3.0, step=12.0, deepabs=-60.0, minleft=90.0, name="s4"):
    """S4: 구간 앞 within 초 안의 gap 초 이상 깊은 무음(절대 deepabs dB) 뒤 음량이 step dB 이상 커지면(앞 10초 중앙값 대비) 거기서 시작. s0 기준(원래 후보 시작)에서 찾는다."""
    def prop(pcm, a, voc, s, e, s0, e0):
        d = dbt(pcm)
        if d is None:
            return s, e
        i0, i1 = int(s / 0.1), int(min(e, s + within + 20) / 0.1)
        x = d[i0:i1]
        best = None
        for v, i, j in runs(x < deepabs):
            if v and (j - i) * 0.1 >= gap and i * 0.1 <= within and j < len(x):
                before = float(np.median(x[max(0, i - 100):i])) if i else None
                after = float(np.median(x[j:j + 100]))
                if before is not None and after - before >= step and e - (i0 + j) * 0.1 >= minleft:
                    best = (i0 + j) * 0.1
        return (best, e) if best is not None and best > s else (s, e)
    prop.__name__ = name
    return prop


# ---------------- 끝 ----------------
def e4(look=8.0, floor=-45.0, spmax=0.2, silmin=0.3, deep=-50.0, maxext=6.0, name="e4"):
    """E4: 끝 e 뒤 look 초 안에 깊은 무음(deep dB 미만 silmin 초)이 오기 전까지 dB>floor & Speech<spmax 인 소리가 이어지면 무음 직전까지 끝을 늘린다(최대 maxext)."""
    def prop(pcm, a, voc, s, e, s0, e0):
        d = dbt(pcm)
        if d is None:
            return s, e
        i0, i1 = int(e / 0.1), int((e + look) / 0.1)
        x = d[i0:i1]
        sil = [r for r in runs(x < deep) if r[0] and (r[2] - r[1]) * 0.1 >= silmin]
        if not sil:
            return s, e
        k = sil[0][1]
        if k * 0.1 < 0.3 or k * 0.1 > maxext:
            return s, e
        seg = x[:k]
        sp = sp_of(a, e, e + k * 0.1)
        if (seg > floor).all() and sp.mean() < spmax:
            return s, e + k * 0.1
        return s, e
    prop.__name__ = name
    return prop


def e5(diff=6.0, near=2.0, maxext=20.0, drop=10.0, deep=-50.0, spmax=0.3, name="e5"):
    """E5: 끝 앞 near 초 중앙 dB 와 끝 뒤 near 초 중앙 dB 의 차가 diff 미만이면(끝이 에너지로 확인 안 됨) 다음 깊은 무음(deep dB)이나 drop dB 급락까지(최대 maxext) 늘린다. 연장 구간 Speech 평균 >= spmax 이면 안 함."""
    def prop(pcm, a, voc, s, e, s0, e0):
        d = dbt(pcm)
        if d is None:
            return s, e
        i = int(e / 0.1); n = int(near / 0.1)
        before, after = float(np.median(d[i - n:i])), float(np.median(d[i:i + n]))
        if before - after >= diff:
            return s, e
        x = d[i:i + int(maxext / 0.1)]
        k = len(x)
        for j in range(0, len(x) - 10):
            if x[j] < deep or float(np.median(x[j:j + 10])) < before - drop:
                k = j
                break
        if k * 0.1 < 1.0 or k >= len(x) - 10:
            return s, e                                   # 못 찾으면(계속 이어짐: BGM 가능) 믿지 않음
        if sp_of(a, e, e + k * 0.1).mean() >= spmax:
            return s, e
        return s, e + k * 0.1
    prop.__name__ = name
    return prop


def seq(*ps, name="seq"):
    """규칙을 순서대로 적용(앞 규칙의 결과를 다음 규칙의 s,e 로)."""
    def prop(pcm, a, voc, s, e, s0, e0):
        for p in ps:
            s, e = p(pcm, a, voc, s, e, s0, e0)
        return s, e
    prop.__name__ = name
    return prop


def selftest():
    class M(np.ndarray):
        filename = "x"
    sr = 16000
    pcm = np.zeros(sr * 100, np.int16)
    pcm[sr * 20:sr * 90] = 3000
    m = pcm.view(M)
    a = np.zeros((200, 3), np.float32); a[40:180, 2] = 0.9
    _T["x"] = 20 * np.log10(np.abs(pcm.reshape(-1, 1600).astype(np.float32) / 32768).mean(1) + 1e-6)
    assert abs(s3()(m, a, None, 40.0, 90.0, 40.0, 90.0)[0] - 20.0) < 0.15, s3()(m, a, None, 40.0, 90.0, 40.0, 90.0)
    assert s3()(m, a, None, 40.0, 90.0, 35.0, 90.0)[0] == 40.0                                  # S1 이 민 곡은 건너뜀
    assert abs(e4()(m, a, None, 0.0, 89.0, 0, 89)[1] - 90.0) < 0.2                              # 무음 직전까지 늘림
    assert e5()(m, a, None, 0.0, 75.0, 0, 75)[1] > 88 and e5()(m, a, None, 0.0, 50.0, 0, 50)[1] == 50.0                                          # 에너지 미확인 끝 -> 무음까지
    print("bound_rules selftest ok")


if __name__ == "__main__":
    selftest()


# ---------------- 음악 구조(SSM novelty) ----------------
_NOV = {}


def novelty_curve(pcm, t0, t1, L=8):
    """[t0,t1) 크로마+MFCC SSM 의 Foote novelty (0.5초 프레임, 최댓값 1). bl_struct.py 와 같은 계산, 같은 (파일, 구간)은 캐시."""
    k = (getattr(pcm, "filename", None), round(t0, 1), round(t1, 1), L)
    if k not in _NOV:
        import bl_struct as B
        y = pcm[int(max(t0, 0) * 16000):int(t1 * 16000)].astype(np.float32) / 32768
        _NOV[k] = B.novelty(B.feats(y), L)
    return _NOV[k]


def nov_start(back=45.0, L=8, zthr=1.0, minmove=1.0, pick="max", mu=0.0, skip_moved=True, name="nov_start"):
    """시작 앞 back 초 안의 novelty 봉우리 중 pick(max=가장 큰, last=가장 가까운) 으로 시작을 당긴다. 사이 Music 평균 < mu 이면 안 함."""
    def prop(pcm, a, voc, s, e, s0, e0):
        if skip_moved and s - s0 > 1.0:
            return s, e
        t0 = max(s - back - 10, 0.0)
        nov = novelty_curve(pcm, t0, s + 10, L)
        z = (nov - nov.mean()) / (nov.std() + 1e-9)
        pk = [i for i in range(1, len(nov) - 1) if nov[i] >= nov[i - 1] and nov[i] > nov[i + 1] and z[i] >= zthr and s - back <= t0 + i * 0.5 <= s - minmove]
        if not pk:
            return s, e
        i = max(pk, key=lambda i: nov[i]) if pick == "max" else pk[-1]
        t = t0 + i * 0.5
        seg = a[int(t / HOP):int(s / HOP)]
        return (t, e) if len(seg) and seg[:, 2].mean() >= mu else (s, e)
    prop.__name__ = name
    return prop
