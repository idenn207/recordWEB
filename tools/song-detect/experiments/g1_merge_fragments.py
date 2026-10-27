"""g1 검수 제안 시험(코드 수정 없음): detect 조각 병합 M1 = 1_detect.json 의 인접 조각(keep 여부 무관, 조각 사이 GAP 초 이하)을
 사이 구간에 깊은 무음(조각 중앙값-30dB 미만 1초 이상)이나 말(Speech>=0.5 가 2초 이상)이 없으면 한 곡으로 합친다(합친 길이 360초 이하).
 근거: blind9 #20 곡(338초)이 보컬 5초 창 비율이 낮은 간주/약한 구간에서 4조각(35~134초)으로 갈라져 하나만 keep, 나머지는 'short' 로 버려졌다. #18 의 꼬리(10478-10483)도 같은 유형.
사용: python experiments/g1_merge_fragments.py [방송슬러그...]  (기본 전부; 합쳐진 목록 출력)"""
import sys, json, glob
sys.path.insert(0, '.')
import numpy as np
from snap import pcm_of, rms_db, HOP
from paths import cache_of
GAP, MAXLEN = 30.0, 360.0
def merge(pcm, a, segs):
    out = []
    for g in sorted(segs, key=lambda g: g['start']):
        if out and g['start'] - out[-1]['end'] <= GAP and g['end'] - out[-1]['start'] <= MAXLEN:
            p = out[-1]; ref = float(np.median(rms_db(pcm, p['start'], p['end'])[1]))
            ts, db = rms_db(pcm, p['end'], g['start'])
            ix = np.minimum((ts / HOP).astype(int), len(a) - 1)
            deep = (db < ref - 30) & (a[ix, 1] < 0.3)
            spk = a[ix, 1] >= 0.5
            def run(m, n):
                c = 0
                for x in m:
                    c = c + 1 if x else 0
                    if c >= n: return True
                return False
            if not run(deep, 10) and not run(spk, 20):
                p['end'] = g['end']; p['parts'] = p.get('parts', 1) + 1; p['keep'] = p['keep'] or g['keep']; continue
        out.append(dict(g, parts=1))
    return out
if __name__ == '__main__':
    names = sys.argv[1:] or [f.replace(chr(92), '/').split('/')[1] for f in sorted(glob.glob('out/20*/1_detect.json'))]
    for v in names:
        w = f'data/vod/nas/{v}.wav'
        try: pcm = pcm_of(w); a = np.load(cache_of(w, '.scores.npy'))
        except Exception: continue
        segs = json.load(open(f'out/{v}/1_detect.json', encoding='utf-8'))
        for m in merge(pcm, a, segs):
            if m['parts'] > 1: print(v, f"{m['start']:.0f}-{m['end']:.0f} ({m['end']-m['start']:.0f}s) parts={m['parts']} keep={m['keep']}")
