"""축 (b) 결정 재생으로 규칙 실험을 초 단위로: 격자 스윕 + 규칙 변형 + 규칙 순서 변경. 전부 등록부를 끈 상태(registry=False)의 N 노출과 라이브(L,B) 손실로 본다.
표본 내 수치다(NAS 10월 191후보, 라벨 L43 B18 N55): 일반화는 축 (c) 그룹 hold-out 에서만 주장한다.
사용: python harness/exp_b.py  -> cache/proto_harness/exp_b.json"""
import itertools, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *
from harness.replay import load_cards, labels, Replayer, metrics
import numpy as np

cards = load_cards(); lab = labels(cards)
rp = Replayer(cards)
out = {}
base = metrics(lab, rp.run(registry=False))
out["base_noreg"] = base
print("기준(등록부 없음)", base)

# H07 격자: rel_db x bursts (n_signals.P)
t = time.perf_counter()
grid, rows_ = [], []
for rel, bu in itertools.product(np.arange(-9.0, -2.9, 0.25), np.arange(1.0, 3.6, 0.1)):
    m = metrics(lab, rp.run(npp=dict(rel_db=float(rel), bursts=float(bu)), registry=False))
    rows_.append((round(float(rel), 2), round(float(bu), 1), m["N_expose"], m["L_loss"] + m["B_loss"], m["L_loss"]))
dt = time.perf_counter() - t
out["grid"] = dict(n=len(rows_), sec=round(dt, 1), per_run_ms=round(dt / len(rows_) * 1000, 1))
ok0 = [r for r in rows_ if r[3] == 0]
best = min(ok0, key=lambda r: (r[2], -r[0]))
cur = next(r for r in rows_ if r[0] == -5.75 and r[1] == 2.1) if any(r[0] == -5.75 and r[1] == 2.1 for r in rows_) else None
out["grid"].update(best_loss0=best, n_loss0=len(ok0), min_expose_any=min(rows_, key=lambda r: r[2]), cur=cur)
print("격자", len(rows_), "조합", f"{dt:.1f}초 ({dt / len(rows_) * 1000:.0f}ms/조합)", "손실 0 중 최소 노출", best, "노출 최소(손실 무시)", out["grid"]["min_expose_any"])
json.dump(rows_, open(PH / "exp_b_grid.json", "w"))

# 규칙 변형: extra 훅(tier 뒤, known_pos 앞) 또는 임계 덮어쓰기
V = {}
def var(name, **kw):
    t = time.perf_counter(); m = metrics(lab, rp.run(registry=False, **kw)); V[name] = dict(m=m, ms=round((time.perf_counter() - t) * 1000)); return m

var("현행", )
var("신호 끔(옛 움직임 대역만)", npp=dict(rel_db=-99.0, bursts=99.0))                       # fire 가 항상 빈 목록 -> weak 없음
var("rel_db 만 (bursts 끔)", npp=dict(bursts=99.0))
var("bursts 만 (rel_db 끔)", npp=dict(rel_db=-99.0))
var("motion 34.5 -> 30", mp=dict(motion=30.0))
var("motion 34.5 -> 40(옛값)", mp=dict(motion=40.0))
var("scene_idle 0.03 -> 0.02", rp=dict(scene_idle=0.02))
var("scene_idle 0.03 -> 0.05", rp=dict(scene_idle=0.05))
var("scene_drop 0.18 -> 0.14", rp=dict(scene_drop=0.14))
var("wait_s 300 -> 600", rp=dict(wait_s=600))


def speech_drop(thr):
    def f(g, c):                                            # speech 가 높으면 likely 제외가 아니라 drop (규칙 순서: 오디오 말소리 게이트를 앞으로)
        if g["tier"] != "drop" and (g.get("speech") or 0) >= thr:
            g["tier"], g["tier_why"] = "drop", f"speech {g['speech']:.2f}"
    return f


def multi_unknown_review_only(g, c):                       # 다중 참조가 live 가 아니면 auto 불가(review 로 강등): 규칙 순서/조합 변경
    if g["tier"] == "auto" and g.get("multi") != "live":
        g["tier"], g["tier_why"] = "review", "multi!=live"


def len_first(g, c):                                       # 길이 게이트를 장면 게이트보다 먼저: 125~340 밖이면 drop
    if g["tier"] != "drop" and not (125 <= g["len"] <= 340):
        g["tier"], g["tier_why"] = "drop", "길이 밖"


var("speech>=0.06 이면 drop", extra=speech_drop(0.06))
var("speech>=0.10 이면 drop", extra=speech_drop(0.10))
var("multi!=live 이면 auto 금지", extra=multi_unknown_review_only)
var("길이 밖이면 drop(길이 게이트 앞당김)", extra=len_first)
out["variants"] = V
for k, v in V.items():
    m = v["m"]; print(f"{k:34} auto {m['auto']:3} review {m['review']:3} drop {m['drop']:3} | N노출 {m['N_expose']:2}/{m['N']} N auto {m['N_auto']} | 라이브손실 L {m['L_loss']} B {m['B_loss']} | {v['ms']}ms")
json.dump(out, open(PH / "exp_b.json", "w"), ensure_ascii=False, indent=1, default=float)
