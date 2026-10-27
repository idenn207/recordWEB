"""등록부(known_negatives) 없이 N(라이브 아님)을 거르는 오디오 신호 2개 (PLAN_NEXT P6). 영상 접근 없이 wav + scores.npy 만으로 계산한다.
  bursts : Speech>0.5 가 1초 이상 이어지는 덩어리 수 / 분 (곡 중간에 말이 끼는 정도. 라이브 곡은 MR 위에서 한 번에 부름)
  rel_db : 곡 구간 중앙값 dBFS - 그 방송의 말소리(Speech>=0.7 프레임) 중앙값 dBFS (BGM 은 말소리보다 훨씬 작게 틀어 둠)
어느 하나라도 임계를 넘으면 g['nsig'] 에 사유를 남기고 route.mark_likely 가 weak(완성본 review 제외) 로 표시한다. drop 이 아니라 표시라서 카드에서 복구할 수 있고, 승인 구간은 known_pos 가 auto 로 올려 영향이 없다.
임계 근거: 알려진 라이브 전부(logo_route 신호 표 88 + 승인 golden 113 중 겹치지 않는 48, 합 136)의 극값 + 약 0.1 x 범위. rel_db 최소 -3.96(범위 17.6) -> -5.7, bursts 최대 1.95(마시로 15827672@17743) -> 2.1.
채택 기준 미달 기록(PLAN_NEXT P6): 목표는 blind9 N 노출 10/55 이하 + 라이브 손실 0 이었으나 둘이 함께 안 된다. 임계를 표(라이브 88)로만 잡으면(bursts 1.3) 노출 10/55 지만 승인 마시로 라이브 1곡이 걸린다. 승인 라이브까지 넣으면
그룹 제외 hold-out 노출 14/55 [11-40%](스트리머 제외 19/55), 라이브 손실 0(움직임 임계 재추정으로 잃는 V15 후야 제외). 현재 규칙(노출 23 + weak 22 숨김)보다는 노출이 줄고 숨던 라이브가 풀려 채택했다. 목표 10/55 는 미달이다.
shortcut: 임계는 스트리머 11명 표본의 극값이라 새 스트리머에서는 라이브가 걸릴 수 있다(걸려도 drop 이 아니라 weak 표시). 표본이 늘면 logo_route.py 로 다시 구한다.
사용: python n_signals.py  (자가검사)"""
from pathlib import Path

P = dict(rel_db=-5.7, bursts=2.1)         # rel_db < 값 이거나 bursts > 값 이면 N 신호
HOP = 0.5                                  # scores.npy 프레임 간격(초)


def fire(g, p=P):
    """사유 목록 (신호가 없는 후보는 None = 판단 불가, 빈 목록 = 신호 없음 통과)"""
    if g.get("rel_db") is None or g.get("bursts") is None:
        return None
    out = []
    if g["rel_db"] < p["rel_db"]:
        out.append(f"말소리보다 {-g['rel_db']:.1f}dB 작음(BGM)")
    if g["bursts"] > p["bursts"]:
        out.append(f"곡 중 말 덩어리 {g['bursts']:.1f}/분")
    return out


def _bursts(sp):
    """sp(Speech 점수 열)에서 1초(2프레임) 이상 연속 >0.5 인 덩어리 수 / 분"""
    import numpy as np
    m = np.r_[False, sp > 0.5, False].astype(np.int8)
    d = np.diff(m)
    run = np.flatnonzero(d == -1) - np.flatnonzero(d == 1)
    return float((run >= 2).sum() / (len(sp) * HOP / 60)) if len(sp) else 0.0


def speech_db(a, pcm):
    """방송의 말소리 음량: Speech>=0.7 프레임(최대 1500개 표본)의 0.5초 rms dBFS 중앙값. 말소리 프레임이 없으면 None"""
    import numpy as np
    idx = np.flatnonzero(a[:, 1] >= 0.7)
    if not len(idx):
        return None
    idx = idx[::max(1, len(idx) // 1500)]
    lv = lambda i: 20 * np.log10(np.sqrt(((pcm[int(i * HOP * 16000):int(i * HOP * 16000) + 8000].astype(np.float32) / 32768) ** 2).mean()) + 1e-9)
    return float(np.median([lv(i) for i in idx]))


def fill(segs, wav):
    """segs 각 구간에 bursts, rel_db 를 채운다. 점수 캐시나 wav 가 없으면 건드리지 않는다(= fire 가 None, 옛 동작). 이미 채워져 있으면 건너뜀"""
    import numpy as np
    from paths import cache_of
    from snap import pcm_of, rms_db
    sc = cache_of(wav, ".scores.npy")
    todo = [g for g in segs if g.get("keep") and (g.get("bursts") is None or g.get("rel_db") is None)]
    if not todo or not Path(sc).exists() or not Path(wav).exists():
        return
    a, pcm = np.load(sc), pcm_of(wav)
    ref = speech_db(a, pcm)
    for g in todo:
        g["bursts"] = _bursts(a[int(g["start"] * 2):min(int(g["end"] * 2), len(a)), 1])
        g["rel_db"] = None if ref is None else float(np.median(rms_db(pcm, g["start"], g["end"])[1])) - ref


if __name__ == "__main__":
    import numpy as np
    assert _bursts(np.array([0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0.], float)) == 2 / (11 * 0.5 / 60)      # 1프레임(0.5초) 덩어리는 센 제외, 2프레임 이상 2개
    assert _bursts(np.zeros(0)) == 0.0
    assert fire({}) is None and fire({"rel_db": 3.0, "bursts": 0.0}) == []
    assert len(fire({"rel_db": -9.0, "bursts": 2.5})) == 2 and len(fire({"rel_db": -5.7, "bursts": 2.1})) == 0     # 경계값은 통과
    print("ok")
