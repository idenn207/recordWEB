"""경계 후처리 (refine.py 와 별도): 구간 끝을 Music 점수가 끊기는 지점(절벽)으로, 시작을 앞 10초 안의 마지막 무음/말 끊김 뒤 첫 소리 - 1초로 맞춘다(lead_start).
- 끝: [끝-8초, 끝+15초] 에서 Music<0.25 가 1.5초 이상 이어지는 첫 지점. 없으면 그대로(연주가 이어지는 곡을 무한정 늘리지 않음).
  랩(Music 0.4~0.7 유지)이나 음악적 종료로 일찍 잘린 끝을 늘리고, 늦게 잡힌 끝은 당긴다.
- 끝은 사용자 규칙: 노래 쪽 경계에서 최대 2초 여유 안의 무음(에너지 낮고 Speech 낮은) 지점으로 스냅.
사용: python snap.py <wav> <segments.json 입력> <출력>     (cache/detect/<이름>.scores.npy 필요: 열 = Singing, Speech, Music, 0.5초 간격)
      python snap.py selftest | evaltable (사용자 경계 표) | evalnana (나나 정답 위치)"""
import json, sys
from pathlib import Path
import numpy as np
from paths import cache_of

HOP, SR, FR = 0.5, 16000, 0.1            # 점수 간격 / 표본률 / 에너지 프레임(초)
BACK, FWD, MARGIN = 8.0, 15.0, 2.0       # 끝 탐색 범위(앞/뒤), 무음 스냅 여유(초)
LOW, RUN = 0.25, 3                       # Music 절벽: 점수<0.25 가 RUN 개(1.5초) 연속


def pcm_of(wav):
    with open(wav, "rb") as f:
        off = f.read(4096).find(b"data") + 8
    return np.memmap(wav, dtype="<i2", mode="r", offset=off)


def rms_db(pcm, t0, t1):
    """[t0,t1) 을 FR 초 프레임으로 나눈 dBFS. (시각 배열, 값 배열)"""
    ts = np.arange(max(0.0, t0), t1, FR)
    x = [pcm[int(t * SR):int((t + FR) * SR)].astype(np.float32) / 32768 for t in ts]
    return ts, np.array([20 * np.log10(np.sqrt((v ** 2).mean() + 1e-12)) for v in x])


def cliff(a, t0, t1):
    """[t0,t1) 에서 Music<LOW 가 RUN 개 연속되는 첫 구간의 시작 시각(Music 이 끊긴 지점). 없으면 None."""
    i0, i1 = int(t0 / HOP), min(int(t1 / HOP), len(a))
    low = a[i0:i1, 2] < LOW
    for i in range(len(low) - RUN + 1):
        if low[i:i + RUN].all():
            return (i0 + i) * HOP + HOP        # 창 i 는 i*0.5 부터 0.975초: 음악이 끝난 쪽 경계는 대략 +0.5
    return None


def quiet(pcm, a, ref_db, t0, t1):
    """[t0,t1) 안의 무음 프레임 시각들: 에너지가 곡 중앙값보다 25dB 낮고 Speech<0.3."""
    ts, db = rms_db(pcm, t0, t1)
    sp = np.array([a[min(int(t / HOP), len(a) - 1), 1] for t in ts])
    return ts[(db < ref_db - 25) & (sp < 0.3)]


LOOK, GAP, HOLE, DROP, SPEECH, MU, LEAD = 10.0, 0.6, 0.5, 20, 0.7, 0.5, 1.0   # 탐색 범위(blind6 최대 늦음 10초), 끊김 최소 길이, 끊김 사이 메움(초), 무음 깊이(dB), 말 판정, 무음일 때 Music 상한, 여유(초)


EXT_MU = 0.25   # 늘린 구간의 Singing+Music 평균 하한(blind6 정상 사례 0.30~0.41, 비음악 0.00~0.22 사례를 가르는 값, 표본 약 14개 근거)


def _clean(m, val, n):
    """m 에서 val 이 아닌 값이 n 개 미만 이어진 구간(양옆이 val 인 경우만, 또는 val=False 일 때 val 구간 자체)을 반대로 뒤집는다."""
    m, i = m.copy(), 0
    while i < len(m):
        j = i
        while j < len(m) and m[j] == m[i]:
            j += 1
        if m[i] != val and j - i < n and (not val or (i > 0 and j < len(m))):
            m[i:j] = val
        i = j
    return m


def lead_start(pcm, a, s, ref_db):
    """시작이 늦게 잡힌 곡의 앞부분 복구: s 앞 LOOK 초에서 '끊김'(곡 중앙값보다 DROP dB 낮고 Music<MU 인 무음, 또는 Speech>=SPEECH 인 말)을 표시하고
    HOLE 초 미만 틈은 메운다. s 에서 거슬러 올라가 처음 만나는 GAP 초 이상 끊김의 끝(= 노래 쪽 첫 소리) - LEAD 초를 시작으로 하되,
    끊김 안의 마지막 말 소리 뒤보다 앞으로는 가지 않는다(말 중간 금지). 끊김이 없으면 s.
    shortcut: 곡 중간의 GAP 초 넘는 쉼표(MR 정지)를 끊김으로 오인하면 그 뒤부터 시작할 수 있다(10개 표본에서는 없었음), 표본이 늘면 재점검."""
    ts, db = rms_db(pcm, s - LOOK, s)
    ix = [min(int(t / HOP), len(a) - 1) for t in ts]
    spk = a[ix, 1] >= SPEECH
    brk = ((db < ref_db - DROP) & (a[ix, 2] < MU)) | spk
    n, h = round(GAP / FR), round(HOLE / FR)
    brk = _clean(_clean(brk, True, h), False, n)        # 짧은 소리 틈 메우고(끊김 합침), 그 뒤 GAP 미만 끊김은 곡 속 쉼표로 보고 지움
    i = len(ts)
    while i > 0 and not brk[i - 1]:
        i -= 1                                           # 뒤에서부터 소리가 이어진 구간
    if i == 0 or i == len(ts):
        return s                                         # 끊김 없음, 또는 s 가 이미 끊김 안(소리 직전)
    i0 = i
    while i0 > 0 and brk[i0 - 1]:
        i0 -= 1                                          # [i0, i) 끊김 구간
    lb = ts[i0] if not spk[i0:i].any() else ts[i0 + np.flatnonzero(spk[i0:i])[-1]] + FR
    st = float(max(ts[i] - LEAD, lb))
    seg = a[int(st / HOP):max(int(s / HOP), int(st / HOP) + 1)]
    return st if (seg[:, 0] + seg[:, 2]).mean() >= EXT_MU else s      # 늘린 구간이 음악/노래가 아니면(말·잡음) 늘리지 않음


B_DB, B_GAP, B_TAIL, B_FWD, B_SP, B_ITER, B_MAXLEN = 6.0, 4.0, 2.5, 15.0, 2, 4, 360.0   # 끝 이음: 절벽 직후 1초 에너지 하한(곡 중앙값 대비 -dB), 음악 사이 최대 틈, 마지막 음악 뒤 여유, 탐색 범위(초), 말 연속 중단(홉)


def bridge(pcm, a, ref, c):
    """_bridge 를 끝이 더 안 움직일 때까지(최대 B_ITER 번, 한 번에 B_FWD 초) 되풀이한다: 하락 뒤 음악이 15초 넘게 이어지는 곡도 따라간다(표본: 토아 3122 가 3번 필요, 4번 안에 안 멈추면 포기)."""
    c0 = c
    for _ in range(B_ITER):
        c2 = _bridge(pcm, a, ref, c)
        if c2 <= c:
            return c
        c = c2
    return c0                                           # 계속 이어지기만 하면 음악 연속(BGM 등)일 수 있어 믿지 않는다


def _bridge(pcm, a, ref, c):
    """절벽 c 가 곡 중간의 짧은 Music 하락(소리는 곡 수준으로 이어짐)이면 그 뒤 음악(Music>=0.5, Speech<0.3)이 B_GAP 초 이내 틈으로 이어지는 마지막 지점 + B_TAIL 로 끝을 옮긴다.
    진짜 끝은 절벽 직후 소리가 곡 중앙값보다 크게 줄어(표본 8개: 끝 -11~-43dB, 하락 +1~+2dB) 옮기지 않는다. 말이 B_SP 홉 이어지면 거기서 멈춘다.
    shortcut: 임계값 -6dB 는 하락 2개/끝 6개 표본 근거(나나 10-06 ong, 토아 Q4), 곡 직후 3초 평균이 같은 음량인 박수/노래가 이어지는 경우는 못 거른다."""
    if np.mean(rms_db(pcm, c, c + 3)[1]) < ref - B_DB:      # 3초 평균: 절벽 직후 1초짜리 박수/외침(+4dB)을 곡 소리로 오인하지 않음(blind9 #112/#113)
        return c
    i0, last, sp = int(c / HOP), None, 0
    for i in range(i0, min(i0 + int(B_FWD / HOP), len(a))):
        sp = sp + 1 if a[i, 1] >= 0.3 else 0
        if sp >= B_SP or (i - (i0 if last is None else last)) * HOP > B_GAP:
            break
        if a[i, 2] >= 0.5 and a[i, 1] < 0.3:
            last = i
    return c if last is None else max(c, last * HOP + B_TAIL)


E1_MU, E1_SP, E1_GAP, E1_MIN, E1_CAP = 0.85, 0.2, 2.0, 4.0, 90.0   # 끝 연장: 끝 프레임이 이 Music/Speech 조건이면 gap 이하 틈으로 이어지는 끝까지, 최소 길이, 90초 안에 안 끝나면 믿지 않음(BGM)


def run_len(a, e):
    """E1: 곡 끝 e 직후부터 (Music>=E1_MU & Speech<E1_SP) 가 E1_GAP 초 이하 틈으로 이어지는 길이. e 에서 이미 아니거나 E1_CAP 안에 안 끝나면(BGM 가능) 0.
    간주(보컬 0, Music 높음)가 detect.gap_s 를 넘어 곡이 둘로 갈린 뒤 앞 조각만 남은 경우를 잇는다(blind9 #24 +46, #26 +49, #49 +30; 근본 해결은 detect gap_s/extend 상한이지만 GPU 재탐지가 필요해 후처리로).
    shortcut: 곡 끝 프레임이 이미 조건을 벗어난 경우(#18, #22)는 못 잇는다. 6초 grace 변형은 #111 에 +6.5초 오탐이라 채택하지 않음."""
    i0 = int(e / HOP)
    if i0 >= len(a) or not (a[i0, 2] >= E1_MU and a[i0, 1] < E1_SP):
        return 0.0
    last, bad = i0, 0
    for k in range(i0, min(len(a), i0 + int(E1_CAP / HOP))):
        if a[k, 2] >= E1_MU and a[k, 1] < E1_SP:
            last, bad = k, 0
        else:
            bad += 1
            if bad * HOP > E1_GAP:
                ext = (last - i0) * HOP
                return ext if ext >= E1_MIN else 0.0
    return 0.0


def deep_end(pcm, a, ref, e, look=40.0, depth=30, minlen=0.4, nxt=4.0, nxt_db=12.0):
    """E3: [e-look, e-1.5] 의 마지막 깊은 무음(곡 중앙값-depth dB 미만, Speech<0.3, minlen 초 이상) 뒤 nxt 초 중앙값이 ref-nxt_db 보다 조용하면 그 무음 시작, 아니면 e.
    곡이 끝난 뒤 되살아난 음악/멘트까지 끝이 따라간 경우를 당긴다(blind9 #60 +33.6 -> +0.3, #112 +6.0 -> +0.4).
    shortcut: 곡 안의 깊은 무음 뒤가 조용한 곡(작은 소리 코다)은 일찍 잘릴 수 있다: 표본 49곡에서는 #36 #140 #142 가 뒤 4초가 -1/-8~0/+2dB 라 걸리지 않음."""
    if e - look < 0:
        return e
    ts, db = rms_db(pcm, e - look, e - 1.5)
    q = (db < ref - depth) & (a[np.minimum((ts / HOP).astype(int), len(a) - 1), 1] < 0.3)
    runs, i = [], 0
    while i < len(q):
        j = i
        while j < len(q) and q[j] == q[i]:
            j += 1
        if q[i] and (j - i) * FR >= minlen:
            runs.append((float(ts[i]), float(ts[j - 1]) + FR))
        i = j
    if not runs:
        return e
    t0, t1 = runs[-1]
    return t0 if np.median(rms_db(pcm, t1, t1 + nxt)[1]) < ref - nxt_db else e


def voc_of(wav):
    """cache/detect/<이름>.vocal.json -> [(구간 시작초, 5초 창별 보컬 비율 배열)]. 없으면 [] (S1/S2 는 쉬어 간다)."""
    f = cache_of(wav, ".vocal.json")
    return [(float(k.split("-")[0]), np.array(r)) for k, r in json.load(open(f)).items()] if Path(f).exists() else []


def vwin(voc, a, t):
    """detect 의 5초 창 (vocal 비율, Speech, Music, 창 시작) - t 가 속한 창. 없으면 None."""
    for s0, r in voc:
        n = int((t - s0) // 5)
        if 0 <= n < len(r):
            k = int((s0 + n * 5) / HOP)
            return float(r[n]), float(a[k:k + 10, 1].mean()), float(a[k:k + 10, 2].mean()), s0 + n * 5
    return None


def start_s1(a, voc, s, e, gap=2.0, vmax=0.35, within=40.0, min_left=90.0, lead=1.0):
    """S1 사운드체크 제외: s 뒤 within 초 안의 마지막 Music<0.3 정지(gap 초 이상)가 끝난 곳 - lead 가 새 시작.
    MR 이 켜졌다 멈췄다 다시 시작하는 앞부분(MR 소리 확인/가사 연습)이 곡에 붙은 경우로, 정지 앞 5초 창들의 vocal 평균<vmax(MR 만 나옴)이고 뒤 곡이 min_left 이상일 때만(blind9 #47 -26, #49 -28, #52 -5.6).
    shortcut: 정지 없이 낮은 MR 이 이어지는 사운드체크(#111)는 못 잡는다. 표본 3건 근거."""
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
    """S2 반주 희박한 앞부분 복구: s 앞으로 5초 창을 거슬러 vocal>=vmin & Music>=mumin & Speech<=spmax 인 창(반주가 희박한 노래/호흡)이 이어지는 만큼 시작을 앞당긴다(최대 maxback 초).
    detect 가 Music>=0.5 를 요구해 빼먹은 앞소절을 되찾는다(blind9 #20 -9.2, #44 -5.5, #127/#128 -14.3).
    shortcut: 이동량이 큰 곡(#127 -14.3초)은 사용자 청취 확인이 필요하다. 전주 MR 이 조용한 곡(#54)은 못 잡는다."""
    new, t = s, s - 2.5
    while s - t < maxback:
        w = vwin(voc, a, t)
        if w is None or not (w[0] >= vmin and w[2] >= mumin and w[1] <= spmax):
            break
        new, t = w[3], w[3] - 2.5
    return new


def snap(pcm, a, s, e, voc=None):
    _, db = rms_db(pcm, s, e)
    ref = float(np.median(db))
    c = cliff(a, e - BACK, e + FWD)
    e2 = bridge(pcm, a, ref, c) if c is not None else e
    if c is not None and e2 > c and e2 - s > B_MAXLEN:                               # detect.P max_len_s: 이어 붙여 곡이 6분을 넘으면 이음을 믿지 않고 원래 절벽 유지
        e2 = c
    q = quiet(pcm, a, ref, e2 - 1, e2 + MARGIN)         # 끝: 음악 끝 앞 1초~뒤 2초 안에서 가장 이른 무음
    if len(q):
        e2 = float(q[0])
    e2 += run_len(a, e2)                                # E1: 간주 뒤 이어지는 노래로 끝 연장
    e2 = deep_end(pcm, a, ref, e2)                      # E3: 곡이 끝난 뒤 되살아난 소리까지 간 끝을 깊은 무음으로 당김
    s2 = lead_start(pcm, a, s, ref)                     # 시작: 앞 LOOK 초 안 마지막 끊김 뒤 첫 소리 - LEAD
    if voc:                                             # vocal.json 이 있을 때만: S1 사운드체크 제외, 아니면 S2 반주 희박한 앞부분 복구
        s1 = start_s1(a, voc, s2, e2)
        s2 = s1 if s1 > s2 else start_s2(a, voc, s2)
    return s2, e2


def trim_front(a, s, e, gap=4.0, within=90.0, min_left=90.0):
    """시험용(snap 에 연결 안 됨): 시작 후 within 초 안에 Music<LOW 가 gap 초 이상 이어진 마지막 틈이 있고 그 뒤가 min_left 이상이면,
    틈이 끝나는 시각을 새 시작으로(앞의 사운드체크/연습 제거). 없으면 s. V21 1건으로만 확인한 가설이다."""
    i0, i1 = int(s / HOP), min(int(e / HOP), len(a))
    low, i, best = a[i0:i1, 2] < LOW, 0, None
    while i < len(low):
        j = i
        while j < len(low) and low[j] == low[i]:
            j += 1
        if low[i] and (j - i) * HOP >= gap and i * HOP <= within and (len(low) - j) * HOP >= min_left:
            best = s + j * HOP
        i = j
    return best if best is not None else s


def selftest():
    a = np.zeros((200, 3), np.float32)
    a[:, 2] = 0.9
    a[100:, 2] = 0.0                                    # 50초에 음악이 끊김
    assert cliff(a, 40, 70) == 50.5
    assert cliff(a, 10, 30) is None                     # 절벽 없으면 늘리지 않음
    b = np.full((400, 3), 0.9, np.float32)
    b[40:60, 2] = 0.0                                   # 20~30초에 10초 틈, 뒤에 170초
    assert trim_front(b, 0, 200) == 30.0
    assert trim_front(b, 0, 200, gap=12) == 0
    sr, pcm = 16000, np.zeros(16000 * 100, np.int16)
    pcm[:sr * 60] = 3000                                # 0~60초 소리(곡 수준)
    d = np.zeros((200, 3), np.float32)
    d[:, 2] = 0.9
    d[80:86, 2] = 0.0                                   # 40~43초 Music 하락, 소리는 계속
    assert bridge(pcm, d, -20.0, 40.0) > 58             # 하락 뒤 소리가 이어지는 곳까지 따라감
    pcm[sr * 40:sr * 45] = 0                            # 같은 자리가 무음이면 진짜 끝: 옮기지 않음
    assert bridge(pcm, d, -20.0, 40.0) == 40.0
    m = np.zeros((200, 3), np.float32)
    m[:, 2] = 0.9
    m[160:, 2] = 0.0                                    # 간주(Music 높고 말 없음)가 80초까지 이어짐
    assert run_len(m, 40.0) == 39.5 and run_len(m, 90.0) == 0.0     # 끝 프레임이 조건 안이면 이어진 길이, 밖이면 0
    m[:, 2] = 0.9                                       # 끝까지 안 끝나면(BGM 가능) 믿지 않음
    assert run_len(m, 10.0) == 0.0
    p2 = np.full(sr * 100, 3000, np.int16)
    p2[sr * 50:sr * 51] = 0                             # 깊은 무음 1초
    z = np.zeros((200, 3), np.float32)
    assert deep_end(p2, z, -20.0, 60.0) == 60.0         # 무음 뒤가 곡 소리 수준이면 그대로(곡 안의 쉼)
    p2[sr * 51:] = 30                                   # 무음 뒤가 계속 조용하면 무음 시작에서 끝
    assert abs(deep_end(p2, z, -20.0, 60.0) - 50.0) < 0.11
    b = np.full((400, 3), 0.9, np.float32)
    b[40:50, 2] = 0.0                                   # 20~25초 MR 정지
    assert start_s1(b, [(0.0, np.full(40, 0.1))], 0.0, 200.0) == 24.0     # 정지 앞이 MR 만이면 정지 뒤 -1초부터
    assert start_s1(b, [(0.0, np.full(40, 0.6))], 0.0, 200.0) == 0.0      # 정지 앞이 노래면 건드리지 않음
    c = np.zeros((400, 3), np.float32)
    c[:, 2] = 0.5
    assert start_s2(c, [(0.0, np.full(20, 0.7))], 50.0) == 20.0           # 희박한 반주 + 노래 창을 최대 30초 거슬러
    assert start_s2(c, [(0.0, np.full(20, 0.3))], 50.0) == 50.0
    print("selftest ok")


USER = dict(V11=(24, 245), V12=(20, 245), V13=(20, 230), V14=(20, 187), V15=(19, 256), V16=(23, 267), V22=(18, 150))  # blind5 사용자 경계(클립 내 상대초, 7개 표본)


START6 = dict(V08=12, V15=15, V22=10)                    # blind6 사용자 시작(클립 내 상대초, 끝 라벨 없음, 3개 표본)


def evaltable():
    """사용자 경계 대비 전/후 오차표(blind5 라이브 7 + blind6 시작 3). 오차 = 탐지 - 사용자(초, 음수 = 이름, 양수 = 앞이 잘림).
    assert: 끝 오차 +-2초(blind5), 시작 후 오차 <= +2 (앞이 잘리는 쪽)."""
    for s, tab in (("blind5", {v: (a, b) for v, (a, b) in USER.items()}), ("blind6", {v: (a, None) for v, a in START6.items()})):
        k = json.load(open("data/review/%s/key.json" % s, encoding="utf8"))
        for v, (a, b) in tab.items():
            w = "data/vod/%s.wav" % k[v]["videoNo"]
            s0, e, c = k[v]["start"], k[v]["end"], k[v]["clip_start"]
            s2, e2 = snap(pcm_of(w), np.load(cache_of(w, ".scores.npy")), s0, e, voc_of(w))
            ee = (" | 끝 전%+.1f 후%+.1f" % (e - c - b, e2 - c - b)) if b else ""
            print(s, v, "시작 전%+.1f 후%+.1f" % (s0 - c - a, s2 - c - a) + ee)
            assert s2 - c - a <= 2, (s, v)
            if b:
                assert -2 <= e2 - c - b <= 2, v


def evalnana(d="cache/exp7b"):
    """나나 정답 위치(data/refs.json, 곡-탐지 일대일 18곡)에 대한 snap 전/후 시작/끝 오차. 시작 앞잘림(>2초)이 늘지 않는지 assert."""
    ov = lambda a, b, c, d: max(0, min(b, d) - max(a, c))
    refs = [r for r in json.load(open("data/refs.json", encoding="utf8")) if not r["title"].endswith("1절")]
    R = []
    for date in ("2026-10-06", "2026-10-16"):
        w = "data/vod/legacy/%s_나나.wav" % date
        pcm, a, voc = pcm_of(w), np.load(cache_of(w, ".scores.npy")), voc_of(w)
        S = [g for g in json.load(open("%s/%s_나나.segments.json" % (d, date), encoding="utf8")) if g["keep"]]
        rs = [r for r in refs if r["date"] == date]
        for r in rs:
            c = [g for g in S if ov(g["start"], g["end"], r["start"], r["end"]) > 0.3 * r["dur"]]
            if len(c) == 1 and sum(ov(c[0]["start"], c[0]["end"], q["start"], q["end"]) > 0.3 * q["dur"] for q in rs) == 1:
                s2, e2 = snap(pcm, a, c[0]["start"], c[0]["end"], voc)
                R.append((c[0]["start"] - r["start"], s2 - r["start"], c[0]["end"] - r["end"], e2 - r["end"]))
    R = np.array(R)
    ok, late = (lambda x: int((abs(x) <= 2).sum())), (lambda x: int((x > 2).sum()))
    print("나나 %d곡 전->후: 시작 +-2초 %d->%d, 앞잘림(>2) %d->%d | 끝 +-2초 %d->%d" % (len(R), ok(R[:, 0]), ok(R[:, 1]), late(R[:, 0]), late(R[:, 1]), ok(R[:, 2]), ok(R[:, 3])))
    assert (R[:, 1] > 2).sum() <= (R[:, 0] > 2).sum()


if __name__ == "__main__":
    if sys.argv[1] == "selftest":
        selftest()
        sys.exit()
    if sys.argv[1] == "evalnana":
        evalnana()
        sys.exit()
    if sys.argv[1] == "evaltable":
        evaltable()
        sys.exit()
    wav, seg_in, seg_out = sys.argv[1:4]
    pcm, a, voc = pcm_of(wav), np.load(cache_of(wav, ".scores.npy")), voc_of(wav)
    segs = json.load(open(seg_in, encoding="utf8"))
    for g in segs:
        if g["keep"]:
            g["start1"], g["end1"] = g["start"], g["end"]
            g["start"], g["end"] = snap(pcm, a, g["start"], g["end"], voc)
            g["len"] = g["end"] - g["start"]
    json.dump(segs, open(seg_out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
