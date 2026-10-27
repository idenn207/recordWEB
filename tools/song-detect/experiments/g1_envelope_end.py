"""g1 검수 제안 시험(코드 수정 없음): 끝 연장 E1b = 끝 뒤로 '곡 소리가 이어지는 한' 따라가는 2단계.
 1단계: Music>=0.5 & Speech<0.3 프레임이 GAP 초 이하 틈으로 이어지는 마지막 지점(E1 의 0.85/0.2, 틈 2초보다 느슨)
 2단계(1단계가 움직였을 때만): 거기서 곡 소리(dB >= 곡 중앙값-12 & Speech<0.3)가 이어지는 동안 더 따라감(조용한 아웃트로, YAMNet 이 Music 을 낮게 보는 곳)
 채택: 최종 지점 직후 1~3초 중앙값이 곡 중앙값-15dB 보다 낮거나 직후 3초 Speech 평균>=0.5(= 소리가 끊기고 멘트/무음이 오는 진짜 끝), 상한 CAP 초, 곡 길이 360초 이하
사용: python experiments/g1_envelope_end.py   (번호별 현재 v4 끝 -> E1b 끝)"""
import sys, json
sys.path.insert(0, '.')
import numpy as np
from snap import pcm_of, rms_db, HOP
from paths import cache_of
MU, SP, CAP, DROPDB, LOUD, GUARD = 0.5, 0.3, 120.0, 15.0, 12.0, 1.0
def e1b(pcm, a, ref, s, e, gap=5.0):
    if float(np.mean(rms_db(pcm, e, e + 3)[1])) < ref - GUARD: return e, 'natural-end'   # 끝 직후 3초가 곡 중앙값보다 GUARD dB 넘게 작으면 자연스러운 끝(감쇠/절벽): 건드리지 않음
    i0 = int(e / HOP); last = i0; bad = 0
    for k in range(i0, min(len(a), i0 + int(CAP / HOP))):
        if a[k, 2] >= MU and a[k, 1] < SP: last, bad = k, 0
        else:
            bad += 1
            if bad * HOP > gap: break
    t = last * HOP + HOP
    if t - e < 2.0: return e, 'no-ext'
    ts, db = rms_db(pcm, t, t + 60)                        # 2단계
    bad, t2 = 0, t
    for j in range(0, len(ts), 5):
        k = min(int(ts[j] / HOP), len(a) - 1)
        if db[j] >= ref - LOUD and a[k, 1] < SP: t2, bad = ts[j], 0
        else:
            bad += 1
            if bad * 0.5 > 3.0: break
    t = max(t, float(t2))
    if t - s > 360: return e, 'too-long'
    after = float(np.median(rms_db(pcm, t + 1.0, t + 3.0)[1]))
    sp = float(a[int(t / HOP):int((t + 3) / HOP), 1].mean())
    return (t, 'cliff') if (after < ref - DROPDB or sp >= 0.5) else (e, 'no-cliff')
if __name__ == '__main__':
    rows = {14:('2026-10-03_rize_1',14648.5,14865.5),18:('2026-10-04_rize_1',10357.7,10464.0),19:('2026-10-04_rize_1',10568.0,10759.2),
            20:('2026-10-04_rize_1',10884.0,11029.5),22:('2026-10-06_nana_1',25197.3,25511.0),23:('2026-10-06_nana_1',28702.2,28911.0),
            25:('2026-10-06_nana_1',29030.6,29232.0),34:('2026-10-09_rize_1',23169.9,23331.8),35:('2026-10-10_nana_2',15896.9,16047.6),36:('2026-10-10_nana_2',16084.2,16289.0)}
    for n, (v, s, e) in rows.items():
        w = f'data/vod/nas/{v}.wav'; pcm = pcm_of(w); a = np.load(cache_of(w, '.scores.npy'))
        ref = float(np.median(rms_db(pcm, s, e)[1]))
        t, why = e1b(pcm, a, ref, s, e)
        print(f'#{n} end {e:.1f} -> {t:.1f} ({t-e:+.1f}s, {why})')

def sweep():
    """전 방송 keep 구간(3_final.json)에 적용해 몇 곡이 얼마나 움직이는지(회귀 점검)."""
    import glob, re
    mv = []
    for f in sorted(glob.glob('out/20*/3_final.json')):
        v = f.replace(chr(92), '/').split('/')[1]
        w = f'data/vod/nas/{v}.wav'
        try: pcm = pcm_of(w); a = np.load(cache_of(w, '.scores.npy'))
        except Exception: continue
        for g in json.load(open(f, encoding='utf-8')):
            if not g.get('keep'): continue
            s, e = g['start'], g['end']
            ref = float(np.median(rms_db(pcm, s, e)[1]))
            t, why = e1b(pcm, a, ref, s, e)
            if t - e >= 2: mv.append((v, round(s), round(e), round(t - e, 1)))
    print(len(mv), 'moved'); [print(x) for x in mv]
if len(sys.argv) > 1 and sys.argv[1] == 'sweep': sweep()
