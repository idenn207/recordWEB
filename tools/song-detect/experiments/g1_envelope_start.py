"""g1 검수 제안 시험(코드 수정 없음): 시작 복구 S3 = 시작 앞의 '무음 경계까지' 이어진 음악(희박한 전주)을 곡에 포함.
 시작 s 에서 거슬러: 프레임이 음악(Music>=0.4 & Speech<0.3) 또는 소리(dB>=곡중앙값-30)인 동안 계속, 깊은 무음(dB<곡중앙값-35 & Speech<0.3, 1초 이상)이나 말(Speech>=0.5)을 만나면 멈춤.
 채택: 멈춘 곳(무음 끝) 이 s 보다 3초 이상 앞이고 BACK(60초) 안이며, 그 사이 Music 평균>=0.5 (S2 가 vocal>=0.6 을 요구해 못 잡는 희박한 전주 대상)
사용: python experiments/g1_envelope_start.py [sweep]"""
import sys, json, glob
sys.path.insert(0, '.')
import numpy as np
from snap import pcm_of, rms_db, HOP
from paths import cache_of
BACK, DEEP, SND = 60.0, 35.0, 30.0
def s3(pcm, a, ref, s, e):
    ts, db = rms_db(pcm, s - BACK, s)
    ix = np.minimum((ts / HOP).astype(int), len(a) - 1)
    sp, mu = a[ix, 1], a[ix, 2]
    deep = (db < ref - DEEP) & (sp < 0.3)
    t0 = s
    i = len(ts) - 1
    while i >= 0:
        if sp[i] >= 0.5 and (sp[max(0, i - 24):i + 1] >= 0.5).all(): break     # 말 판정은 2.5초 연속일 때만(노래 한 소절이 Speech 로 튀는 1~2초 오탐 무시)
        if deep[i]:                      # 깊은 무음: 1초(10프레임) 이상 이어지면 경계
            j = i
            while j >= 0 and deep[j]: j -= 1
            if i - j >= 10: t0 = float(ts[i]) + 0.1; break
        i -= 1
    else:
        return s, 'no-silence'
    if i < 0 or s - t0 < 3.0: return s, 'no-move'
    seg = mu[(ts >= t0) & (ts < s)]
    return (t0, 'ok') if seg.mean() >= 0.5 else (s, 'not-music')
if __name__ == '__main__':
    rows = {14:('2026-10-03_rize_1',14648.5,14865.5),18:('2026-10-04_rize_1',10357.7,10464.0),19:('2026-10-04_rize_1',10568.0,10759.2),
            20:('2026-10-04_rize_1',10884.0,11029.5),22:('2026-10-06_nana_1',25197.3,25511.0),23:('2026-10-06_nana_1',28702.2,28911.0),
            25:('2026-10-06_nana_1',29030.6,29232.0),34:('2026-10-09_rize_1',23169.9,23331.8),35:('2026-10-10_nana_2',15896.9,16047.6),36:('2026-10-10_nana_2',16084.2,16289.0)}
    for n, (v, s, e) in rows.items():
        w = f'data/vod/nas/{v}.wav'; pcm = pcm_of(w); a = np.load(cache_of(w, '.scores.npy'))
        ref = float(np.median(rms_db(pcm, s, e)[1]))
        t, why = s3(pcm, a, ref, s, e); print(f'#{n} start {s:.1f} -> {t:.1f} ({t-s:+.1f}s, {why})')
    if 'sweep' in sys.argv:
        mv = []
        for f in sorted(glob.glob('out/20*/3_final.json')):
            v = f.replace(chr(92), '/').split('/')[1]; w = f'data/vod/nas/{v}.wav'
            try: pcm = pcm_of(w); a = np.load(cache_of(w, '.scores.npy'))
            except Exception: continue
            for g in json.load(open(f, encoding='utf-8')):
                if not g.get('keep'): continue
                s, e = g['start'], g['end']; ref = float(np.median(rms_db(pcm, s, e)[1]))
                t, why = s3(pcm, a, ref, s, e)
                if s - t >= 3: mv.append((v, round(s), round(e), round(t - s, 1)))
        print(len(mv), 'moved'); [print(x) for x in mv]
