"""카운트인(드럼/하이햇 도입) 탐지 실험 - 파이프라인에 연결 안 됨, 기본값 비활성(snap.lead_start 는 큰 소리 직전 -1초만 잡아 약한 카운트인을 놓친다).
규칙: 시작 s 앞 WIN 초의 고역(4~8kHz, 16kHz 표본이라 8k 가 상한) 프레임 에너지에서 바닥(하위 20%)보다 RISE dB 이상 솟은 국소 최대 = 틱.
s 에서 거슬러 올라가며 간격이 [0.25,1.0]초이고 직전 간격과 비율이 1(±15%) 또는 2배/절반(박 배수 전환, 2+4 박)인 틱 연결이 MIN_TICKS 개 이상이고,
마지막 틱이 s 에서 LAST_GAP 초 안이며 그 구간이 말(Speech>=0.5)이 아니면 새 시작 = 첫 틱 - PRE. 아니면 None.
shortcut: 16kHz wav 라 5~12kHz 대역 대신 4~8kHz, 틱 간격이 불규칙한 필인/루바토 도입은 놓침, 박수/키보드 같은 규칙적 클릭은 '곡 직전'+'말 아님' 조건만으로 막으므로 표본이 늘면 재점검.
사용: python lead_in.py selftest | eval"""
import sys
import numpy as np

SR, N, H = 16000, 512, 160            # 32ms 창, 10ms 홉
WIN, RISE, MIN_TICKS, LAST_GAP, PRE, QUIET = 7.0, 15.0, 4, 1.0, 0.2, 20.0   # QUIET: 틱 구간 평균 음량이 곡보다 이만큼(dB) 작아야 '약한 카운트인'
HOP = 0.5                              # scores.npy 간격


def hi_db(pcm, t0, t1):
    t0 = max(0.0, t0)
    x = np.asarray(pcm[int(t0 * SR):int(t1 * SR)], np.float32) / 32768
    w, fq = np.hanning(N), np.fft.rfftfreq(N, 1 / SR)
    m = fq >= 4000
    e = [20 * np.log10(np.sqrt((np.abs(np.fft.rfft(x[i:i + N] * w))[m] ** 2).sum()) / N + 1e-9) for i in range(0, len(x) - N, H)]
    return t0, np.array(e)


def ticks(pcm, s):
    t0, e = hi_db(pcm, s - WIN, s)
    if len(e) < 50:
        return []
    fl = np.percentile(e, 20)
    pk = [i for i in range(1, len(e) - 1) if e[i] >= e[i - 1] and e[i] > e[i + 1] and e[i] > fl + RISE]
    out = []
    for i in pk:                                       # 220ms 안 중복 봉우리는 하나로
        if not out or i - out[-1] > 22:
            out.append(i)
    return [t0 + i * H / SR for i in out]


def chain(ts):
    """끝(곡 쪽)에서 거슬러 올라가며 규칙적 간격으로 이어진 틱 리스트(시간순). 없으면 []."""
    c, prev = [ts[-1]], None
    for t in ts[-2::-1]:
        d = c[-1] - t
        r = d / prev if prev else 1
        if not (0.25 <= d <= 1.0 and (0.85 <= r <= 1.18 or 0.4 <= r <= 0.6 or 1.6 <= r <= 2.5)):
            break
        c.append(t)
        prev = d
    return c[::-1]


def onset(pcm, s):
    """s 근처 '본 소리' 시작: 전대역 에너지가 곡 수준(s 뒤 3초 중앙값)보다 15dB 이내로 큰 연속 구간(0.3초 미만 틈은 메움)의 시작. 못 찾거나 곡 한가운데면 None."""
    x = np.asarray(pcm[int(max(0, s - 4) * SR):int((s + 3) * SR)], np.float32) / 32768
    f = SR // 20
    db = 20 * np.log10(np.sqrt((x[:len(x) // f * f].reshape(-1, f) ** 2).mean(1)) + 1e-9)
    t0, k = max(0, s - 4), int(round(min(s, 4) * 20))
    thr = np.median(db[k:k + 60]) - 15
    loud = db > thr
    j = next((i for i in range(k, len(db)) if loud[i]), None)
    if j is None:
        return None
    while any(loud[max(0, j - 6):j]):
        j = max(i for i in range(max(0, j - 6), j) if loud[i])
        while j > 0 and loud[j - 1]:
            j -= 1
    return None if j == 0 else t0 + j / 20      # 창 맨 앞까지 계속 큰 소리면 곡 한가운데라 시작점이 아님


def count_in(pcm, start, a=None):
    """start 앞의 카운트인이 보이면 새 시작(초), 아니면 None. a = scores(Singing, Speech, Music), 있으면 틱 구간이 말이 아닌지 확인."""
    start = onset(pcm, start)
    if start is None:
        return None
    ts = [t for t in ticks(pcm, start) if t < start - 0.25]   # 본 소리 직전 0.25초는 곡의 상승부라 제외
    if len(ts) < MIN_TICKS:
        return None
    c = chain(ts)
    if len(c) < MIN_TICKS or start - c[-1] > LAST_GAP:
        return None
    z = lambda u, v: 20 * np.log10(np.sqrt((np.asarray(pcm[int(u * SR):int(v * SR)], np.float32) ** 2).mean()) / 32768 + 1e-9)
    if z(c[0], start) > z(start, start + 3) - QUIET:
        return None
    if a is not None:
        i0, i1 = int((c[0] - 0.5) / HOP), min(int(start / HOP), len(a))
        if (a[i0:i1, 1] >= 0.5).any():
            return None
    return c[0] - PRE


def selftest():
    pcm = np.zeros(SR * 20, np.int16)
    rng = np.random.default_rng(0)
    for t in (6.0, 6.7, 7.4, 7.76, 8.12):               # 약한 고역 틱 2+3
        pcm[int(t * SR):int(t * SR) + 400] = (rng.standard_normal(400) * 300).astype(np.int16)
    pcm[int(SR * 8.5):] = (rng.standard_normal(len(pcm) - int(SR * 8.5)) * 3000).astype(np.int16)   # 곡 시작
    r = count_in(pcm, 8.6)
    assert r is not None and abs(r - 5.8) < 0.1, r
    assert abs(count_in(pcm, 12.0) - 5.8) < 0.1         # 시작이 곡 안쪽이어도 본 소리 시작(8.5)에 맞춤
    far = pcm.copy()
    far[int(SR * 8.5):int(SR * 15)] = 0
    far[int(SR * 15):] = (rng.standard_normal(len(far) - int(SR * 15)) * 3000).astype(np.int16)
    assert count_in(far, 15.2) is None                  # 마지막 틱이 본 소리에서 너무 멀다
    q = np.zeros(SR * 20, np.int16)
    for t in (4.0, 5.9, 6.5, 8.3):                      # 불규칙 클릭
        q[int(t * SR):int(t * SR) + 400] = (rng.standard_normal(400) * 300).astype(np.int16)
    assert count_in(q, 8.6) is None
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1] == "selftest":
        selftest()


def evaluate():
    """평가 표본(experiments/exp14_items, 읽기만)에서 snap 시작 오차 전/후(초, 탐지-정답). 규칙은 snap 결과 s2 에 적용."""
    sys.path.insert(0, "experiments")
    import snap
    from exp14_items import items
    from paths import cache_of
    P, fired, rows = {}, 0, []
    for n, w, s, e, ts, te in items():
        if ts is None:
            continue
        if w not in P:
            P[w] = (snap.pcm_of(w), np.load(cache_of(w, ".scores.npy")))
        s2, _ = snap.snap(*P[w], s, e)
        r = count_in(P[w][0], s2, P[w][1])
        rows.append((n, s2 - ts, None if r is None else r - ts, len(ticks(P[w][0], s2))))
        fired += r is not None
        print("%-22s 전%+6.1f 후%s ticks=%d" % (n, s2 - ts, "  -   " if r is None else "%+6.1f" % (r - ts), rows[-1][3]))
    b = np.array([r[1] for r in rows])
    f = np.array([r[2] if r[2] is not None else r[1] for r in rows])
    print("표본 %d, 발동 %d | 전 |오차|<=2 %d 앞잘림(>2) %d 이름(<-2) %d | 후 %d %d %d" % (len(rows), fired, (abs(b) <= 2).sum(), (b > 2).sum(), (b < -2).sum(), (abs(f) <= 2).sum(), (f > 2).sum(), (f < -2).sum()))


if __name__ == "__main__" and sys.argv[1] == "eval":
    evaluate()
