"""g1 검수 제안 시험(코드 수정 없음): 시작 S4 = 구간 앞부분(WITHIN 초 안)에 깊은 무음(GAP 초 이상) 뒤로 음량이 STEP dB 이상 커지면 그 무음 끝에서 시작.
근거: blind9 #33(아카네리제 10-09) 앞 60초는 작은 소리(-45dB)의 배경음악+멘트이고 사용자가 말한 라이브 시작(01:00)은 -95dB 무음 뒤 -28dB 로 갑자기 커지는 지점(22620.5).
S1(MR 정지 뒤) 은 정지 앞 vocal<0.35 와 within 40초를 요구해 BGM 곡(보컬 0.9)과 60초 거리에서 못 잡는다.
사용: python experiments/g1_level_step_start.py [sweep]"""
import sys, json, glob
sys.path.insert(0, '.')
import numpy as np
from snap import pcm_of, rms_db, HOP
from paths import cache_of
WITHIN, GAP, STEP, DEEP, MINLEFT = 90.0, 3.0, 12.0, 30.0, 90.0
def s4(pcm, a, ref, s, e):
    ts, db = rms_db(pcm, s, min(e, s + WITHIN + 20))
    deep = db < -60                      # 절대 -60dBFS: 무음(곡 중앙값이 낮은 BGM 구간도 포함하려고 상대값 대신)
    i, best = 0, None
    while i < len(deep):
        j = i
        while j < len(deep) and deep[j] == deep[i]: j += 1
        if deep[i] and (j - i) * 0.1 >= GAP and ts[i] - s <= WITHIN and j < len(deep):
            before = float(np.median(db[max(0, i - 100):i])) if i > 0 else None     # 앞 10초 중앙값
            after = float(np.median(db[j:j + 100]))
            if before is not None and after - before >= STEP and e - ts[j] >= MINLEFT: best = float(ts[j])
        i = j
    return best if best is not None else s
if __name__ == '__main__':
    rows = {14:('2026-10-03_rize_1',14648.5,14865.5),18:('2026-10-04_rize_1',10357.7,10464.0),19:('2026-10-04_rize_1',10568.0,10759.2),20:('2026-10-04_rize_1',10884.0,11029.5),
            22:('2026-10-06_nana_1',25197.3,25511.0),23:('2026-10-06_nana_1',28702.2,28911.0),25:('2026-10-06_nana_1',29030.6,29232.0),33:('2026-10-09_rize_1',22560.7,22778.1),
            34:('2026-10-09_rize_1',23169.9,23331.8),35:('2026-10-10_nana_2',15896.9,16047.6),36:('2026-10-10_nana_2',16084.2,16289.0)}
    for n,(v,s,e) in rows.items():
        w=f'data/vod/nas/{v}.wav'; pcm=pcm_of(w); a=np.load(cache_of(w,'.scores.npy')); ref=float(np.median(rms_db(pcm,s,e)[1]))
        print(f'#{n} start {s:.1f} -> {s4(pcm,a,ref,s,e):.1f}')
    if 'sweep' in sys.argv:
        mv=[]
        for f in sorted(glob.glob('out/20*/3_final.json')):
            v=f.replace(chr(92),'/').split('/')[1]; w=f'data/vod/nas/{v}.wav'
            try: pcm=pcm_of(w); a=np.load(cache_of(w,'.scores.npy'))
            except Exception: continue
            for g in json.load(open(f,encoding='utf-8')):
                if not g.get('keep'): continue
                s,e=g['start'],g['end']; ref=float(np.median(rms_db(pcm,s,e)[1])); t=s4(pcm,a,ref,s,e)
                if t-s>=3: mv.append((v,round(s),round(e),round(t-s,1)))
        print(len(mv),'moved'); [print(x) for x in mv]
