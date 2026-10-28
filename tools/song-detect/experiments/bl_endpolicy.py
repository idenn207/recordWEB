"""(f) 끝 처리 정책 비교: 말소리 유입량(초)과 곡 꼬리 손실(초)을 같은 곡 집합에서 정책별로 잰다. 곡 소리는 깎지 않는다(페이드는 곡 끝 이후에만).
곡 집합 = golden 113곡 + 메모 라이브 곡(L/B). 곡 경계(song_e)와 여유 컷(ce)은 현재 코드(audit_engine.calc)의 값.
지표(곡 끝 e, 컷 c, 곡 중앙값 ref, 0.1초 프레임):
  leak     = [e, c) 에서 Speech>0.15 이고 dB>ref-25 인 프레임 초(말소리 유입, 페이드 전)
  leak_a   = 같은 프레임인데 페이드(e 에서 시작, 길이 L, 선형)로 깎인 뒤에도 dB+20log10(gain) > ref-25 인 초(페이드 후에도 들리는 말소리)
  tail_loss= (c 이후로 말 없이(Speech<=0.15) dB>=ref-30 이 이어지는 초, 최대 3초) + (컷 안에서 페이드로 6dB 넘게 깎인 말 없는 꼬리 초): 곡 꼬리/잔향이 잘리거나 깎인 양
사용: python experiments/bl_endpolicy.py"""
import sys; sys.path.insert(0, 'experiments')
from bound_lab import *
import audit_engine as E, make_final as MF
from snap import rms_db, HOP


def songs():
    exp = M.jl(M.EXP)
    G_ = json.load(open(G.GOLD, encoding="utf8"))["songs"]
    todo = {(e["vid"], round(e["refine"][0], 1), round(e["refine"][1], 1)) for e in G_}
    for g in exp["groups"]:
        if g["lab"] == "N":
            continue
        for c in E.kept(g["vno"]):
            o = E.calc(g["vno"], c["start"], c["end"])
            if M.ov(o["song_s"], o["song_e"], *g["base"]) > 0.5 * (g["base"][1] - g["base"][0]):
                todo.add((g["vno"], round(c["start"], 1), round(c["end"], 1)))
    return sorted(todo)


def measure(pcm, a, ref, e, c, L):
    ts, db = rms_db(pcm, e, max(c, e + 0.2) + 3.0)
    ix = np.clip(np.round((ts - 0.4875) / HOP).astype(int), 0, len(a) - 1)
    spk = a[ix, 1] > 0.15
    n = int(round((c - e) / 0.1))
    inw = spk[:n] & (db[:n] > ref - 25)
    gain = np.clip(1 - (ts[:n] - e) / max(L, 1e-6), 0, 1)
    aud = inw & (db[:n] + 20 * np.log10(gain + 1e-6) > ref - 25)
    k, tl = n, 0
    while k < len(ts) and k - n < 30 and not spk[k] and db[k] >= ref - 30:
        k += 1
    mut = ((~spk[:n]) & (db[:n] >= ref - 30) & (gain < 0.5)).sum() * 0.1      # 말 없는 곡 꼬리 소리가 페이드로 6dB 넘게 깎인 초
    return inw.sum() * 0.1, aud.sum() * 0.1, (k - n) * 0.1 + mut


if __name__ == "__main__":
    S = songs()
    rows = {}
    for vid, rs, re_ in S:
        pcm, a, voc = E.wdata(vid)
        o = E.calc(vid, rs, re_)
        o0 = E.calc(vid, rs, re_, tail=False)
        ref = float(np.median(rms_db(pcm, o["song_s"], o["song_e"])[1]))
        e = o["song_e"]
        cuts = {"현재(TAIL+연장)": o["clip_e"], "여유컷만(tail 가드 없음)": o0["clip_e"], "고정 +0.3": e + 0.3, "고정 +1.0 (v4)": max(o0["clip_e"], e + 1.0), "고정 +2.0": max(o0["clip_e"], e + 2.0)}
        # 말 직전 컷 변형: TAIL_MIN 0.0 / 0.3 / 0.5 (말이 곡 끝 직후 시작할 때 얼마나 남기나)
        for mn in (0.0, 0.15, 0.5):
            old = MF.TAIL_MIN; MF.TAIL_MIN = mn
            cuts[f"말 직전 컷(최소 +{mn:g})"] = MF.tail_cut(pcm, a, ref, e, o0["clip_e"]); MF.TAIL_MIN = old
        old = MF.TAIL_EXT; MF.TAIL_EXT = 6.0
        cuts["현재 + 연장 상한 6초"] = MF.tail_cut(pcm, a, ref, e, o0["clip_e"]); MF.TAIL_EXT = old
        for pol, c in cuts.items():
            for L in (0.3, 0.5, 1.0, 1.5):
                Lc = min(L, max(c - e, 0.05))              # 페이드는 컷에서 끝난다(길이 L 이 컷-끝보다 길면 컷-끝)
                lk, la, tl = measure(pcm, a, ref, e, c, Lc)
                rows.setdefault((pol, L), []).append((lk, la, tl, c - e))
        if len(E._W) > 2: E._W.clear()
    print(f"곡 {len(S)}개")
    print(f"{'정책':26s} {'페이드L':>6s} {'평균컷-끝':>8s} {'유입곡':>6s} {'유입초합':>8s} {'페이드후 들림곡':>12s} {'들림초합':>8s} {'꼬리손실곡':>9s} {'손실초합':>8s}")
    out = []
    for (pol, L), v in rows.items():
        v = np.array(v)
        line = dict(pol=pol, L=L, mean_pad=round(float(v[:, 3].mean()), 2), leak_n=int((v[:, 0] > 0).sum()), leak_s=round(float(v[:, 0].sum()), 1), aud_n=int((v[:, 1] > 0).sum()), aud_s=round(float(v[:, 1].sum()), 1), loss_n=int((v[:, 2] > 0.2).sum()), loss_s=round(float(v[:, 2].sum()), 1))
        out.append(line)
        print(f"{pol:26s} {L:6.1f} {line['mean_pad']:8.2f} {line['leak_n']:6d} {line['leak_s']:8.1f} {line['aud_n']:12d} {line['aud_s']:8.1f} {line['loss_n']:9d} {line['loss_s']:8.1f}")
    (OUT / "endpolicy.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf8")
