"""(g) 승인 시작이 음악 시작보다 늦은 곡(unresolved): 규칙은 바꾸지 않고, 두 정책(전주 포함 = S3 제안 시작 사용 / 제외 = 현재 승인 시작 유지)별 영향만 잰다.
대상 = golden 113곡 중 S3(back60, thr-60, 사이 말 비율 가드 0.4)가 시작을 10초 넘게 앞으로 당기는 곡. 영향 = 추가되는 앞부분의 길이, 그 안의 음악(Music>=0.5) 비율/말(Speech>=0.5) 비율/dB 중앙값(곡 중앙값 대비), 클립 길이 변화.
사용: python experiments/bl_unres.py"""
import sys; sys.path.insert(0, 'experiments')
from bound_lab import *
import audit_engine as E, bound_rules as R
from snap import HOP

rows = []
for e in json.load(open(G.GOLD, encoding="utf8"))["songs"]:
    vid, rs, re_ = e["vid"], *e["refine"]
    pcm, a, voc = E.wdata(vid)
    o = E.calc(vid, rs, re_)
    s, en = o["song_s"], o["song_e"]
    for name, p in (("S3 back60 thr-60", R.s3(back=60, thr=-60.0)), ("S3 back30 thr-50", R.s3())):
        t, _ = p(pcm, a, voc, s, en, rs, re_)
        if s - t >= 10 if name.startswith("S3 back60") else s - t >= 2:
            seg = a[int(t / HOP):int(s / HOP)]
            d = R.dbt(pcm); ref = R.ref_of(pcm, s, en)
            x = d[int(t / 0.1):int(s / 0.1)]
            rows.append(dict(id=e["id"], src=e["src"][0][:24], rule=name, shift=round(t - s, 1), music=round(float((seg[:, 2] >= 0.5).mean()), 2), speech=round(float((seg[:, 1] >= 0.5).mean()), 2), med_db=round(float(np.median(x) - ref), 1),
                             truth=e["truth"], frozen_err=e["frozen"].get("err"), clip=round(o["clip_e"] - o["clip_s"], 1)))
    if len(E._W) > 2: E._W.clear()
print(f"{'곡':28s} {'규칙':18s} {'이동':>6s} {'음악':>5s} {'말':>5s} {'dB(곡대비)':>9s} 정답오차(현재) 출처")
for r in rows:
    print(f"{r['id']:28s} {r['rule']:18s} {r['shift']:6.1f} {r['music']:5.2f} {r['speech']:5.2f} {r['med_db']:9.1f} {r['frozen_err']} {r['src']}")
(OUT / "unresolved.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf8")
