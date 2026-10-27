"""python test_route.py"""
from route import tier

seg = lambda **k: {"keep": True, "len": 200, "scene": 0.04, **k}
assert tier(seg(), True)[0] == "auto"
assert tier(seg(keep=False, why="short"), True) == ("drop", "short")
assert tier(seg(piano=True), False)[0] == "optional" and tier(seg(piano=False), True)[0] == "auto"   # piano_gate 표시가 있을 때만 optional(기본 클립 제외)
assert tier(seg(piano=True, start=3), True)[0] == "drop"      # 대기시간이 우선
assert tier(seg(scene=0.30), True)[0] == "drop"            # 같이 보기/영상 시청 화면
assert tier(seg(scene=0.30, multi="live"), True)[0] == "review"  # 다중 참조가 watch/idle 이 아니면 멀어도 review
assert tier(seg(scene=0.30, multi="unknown"), True)[0] == "review"
assert tier(seg(scene=0.30), False)[0] == "review"         # 새 채널은 기준이 없어 판단 보류
assert tier(seg(scene=0.10), True)[0] == "review"          # 애매한 장면(콘서트 0.08~0.12 대)
assert tier(seg(scene=0.010), True)[0] == "review"        # 대기 화면(기준 프레임 오염으로 거리가 0에 가까움)
assert tier(seg(start=3), True)[0] == "drop"               # 방송 시작 5분은 대기시간(곡을 틀어둠)
assert tier(seg(scene=None), True)[0] == "review"          # 장면을 못 읽으면 통과시키지 않는다
assert tier(seg(len=100), True)[0] == "review"             # 1절 또는 짧은 랩
assert tier(seg(len=400), True)[0] == "review"             # 곡 합쳐짐 의심
assert tier(seg(multi="watch"), False) == ("drop", "다중 참조: watch")   # 기준 없는 새 채널도 같이 보기는 drop
assert tier(seg(multi="idle", scene=None), True)[0] == "drop"              # 대기 화면
assert "다중" in tier(seg(multi="live"), False)[1] and tier(seg(multi="live"), False)[0] == "review"   # live 라도 새 채널은 auto 금지
assert tier(seg(multi="unknown"), False)[0] == "review"
assert tier(seg(multi="live"), True)[0] == "auto"          # 기존 채널 기준 경로는 그대로
from route import known_neg
g = seg(start=5040, end=5170, tier="auto")                 # 확인된 비대상(blind7 A)과 겹치면 drop
known_neg(15761307, g); assert g["tier"] == "drop"
g = seg(start=5040, end=5170, tier="auto"); known_neg(1, g); assert g["tier"] == "auto"
print("ok")
# 기준 풀 분할이 평가 대상을 새지 않는지 (scene_pool.excluder)
from scene_pool import excluder
M = [dict(id=i, videoNo=b, name=n, start=s) for i, b, n, s in [("a", 1, "x", 10), ("b", 1, "x", 20), ("c", 1, "x", 30), ("d", 2, "x", 5), ("e", 3, "y", 5)]]
ids = lambda u, m: {o["id"] for o in M if excluder(u, m, M)(o)}
assert ids("broadcast", M[1]) == {"d", "e"} and ids("streamer", M[1]) == {"e"} and ids("clip", M[1]) == {"a", "c", "d", "e"}
assert ids("prev1", M[2]) == {"b", "d", "e"} and ids("prev1", M[0]) == {"d", "e"}   # 바로 앞 형제 1개만, 첫 클립은 형제 없음
D = [dict(id="a", name="x", date="2026-10-06"), dict(id="b", name="x", date="2026-10-16"), dict(id="c", name="y", date="2026-10-06"), dict(id="d", name="x")]
assert {o["id"] for o in D if excluder("date", dict(name="x", date="2026-10-06"), D)(o)} == {"b", "c", "d"}   # 같은 스트리머+날짜(NAS 방송 자신)만 빠진다, 날짜 모르는 항목은 남는다
print("pool ok")
# 승인 이력 자격 (scene_pool.eligible): 5곡 이상 + 서로 다른 방송 2개 이상, 자기 방송만 빼고 세는 keep 도 지원
from scene_pool import eligible
H = lambda n, b: [dict(name="x", videoNo=i % b, live=True) for i in range(n)]
assert not eligible(H(1, 1), "x") and not eligible(H(12, 1), "x") and not eligible(H(4, 4), "x")   # 1곡, 한 방송에만 쌓임, 곡 수 부족
assert eligible(H(5, 2), "x") and not eligible(H(5, 2), "y") and not eligible(H(5, 2), "x", lambda m: m["videoNo"] == 0)   # 방송 하나를 빼면 자격 상실
assert not eligible(H(5, 2) + [dict(name="x", videoNo=9, live=False)] * 9, "x", lambda m: m["videoNo"] != 1)   # 오탐 항목은 세지 않음
print("eligible ok")
from route import known_pos
import json, tempfile, os
f = tempfile.mktemp(suffix=".json"); json.dump([dict(videoNo=7, start=100, end=300, src="t")], open(f, "w"))
g = seg(start=108, end=290, tier="review"); known_pos(7, g, f); assert g["tier"] == "auto"
g = seg(start=120, end=290, tier="review"); known_pos(8, g, f); assert g["tier"] == "review"          # 다른 방송
g = seg(start=120, end=290, tier="drop"); known_pos(7, g, f); assert g["tier"] == "drop"            # drop 은 승인으로도 못 뒤집음
g = seg(start=250, end=500, tier="review"); known_pos(7, g, f); assert g["tier"] == "review"        # 절반 미만 겹침
g = seg(start=120, end=290, tier="review"); known_pos(7, g, f); assert g["ref_bd"] == [20, -10] and g["tier"] == "auto"       # 경계 정답이 아닌 승인 항목(src t = 탐지 당시 값)은 경계가 어긋나도 auto (D3: V16 마시로 +38초)
g = seg(start=105, end=290, tier="review"); known_pos(7, g, f); assert g["tier"] == "auto" and g["ref_bd"] == [5, -10]
os.remove(f)
# 경계 정답이 있는 항목(재생목록 위치 정답 / boundary_ok=True)만 10초 넘게 어긋나면 auto 아님. 겹치는 항목이 여럿이면 하나라도 맞으면 auto, 등록 순서 무관(D5: #45)
PL, OK = dict(videoNo=7, start=100, end=300, src="재생목록 위치 정답"), dict(videoNo=7, start=120, end=290, src="blind9 사용자 라이브", boundary_ok=True)
def kp(ents, **k):
    json.dump(ents, open(f, "w")); g = seg(start=120, end=290, tier="review", **k); known_pos(7, g, f); return g
g = kp([PL]); assert g["tier"] == "review" and g["ref_bd"] == [20, -10] and "경계 어긋남" in g["tier_why"]
assert kp([PL, OK])["tier"] == "auto" and kp([OK, PL])["tier"] == "auto" and kp([PL, OK])["ref_bd"] == [0, 0]
B = dict(OK, boundary_ok=False)
g = kp([B]); assert g["tier"] == "review" and "경계 문제" in g["tier_why"] and "ref_bd" not in g
assert kp([PL, B])["tier"] == "review" and kp([B, dict(PL, start=118, end=292)])["tier"] == "auto"   # B 는 auto 근거가 아니고, 다른 맞는 항목을 가리지도 않는다
# 영상 움직임 drop 면제(D1): 승인 구간과 80% 이상 겹칠 때만, 움직임 drop 에 한해서
mv = dict(multi="live", tstd=35.7)
g = seg(start=120, end=290, **mv); g["tier"], g["tier_why"] = tier(g, True); assert g["tier"] == "drop" and "움직임" in g["tier_why"]
json.dump([OK], open(f, "w")); known_pos(7, g, f); assert g["tier"] == "auto" and "면제" in g["tier_why"]
g = seg(start=120, end=290, **mv); g["tier"], g["tier_why"] = tier(g, True); json.dump([dict(OK, start=100, end=180)], open(f, "w")); known_pos(7, g, f); assert g["tier"] == "drop"   # 겹침 60/min(170,80)=75% < 80%
g = seg(start=120, end=290, **mv); g["tier"], g["tier_why"] = tier(g, True); json.dump([B], open(f, "w")); known_pos(7, g, f); assert g["tier"] == "review"    # 라이브 확인(B)이면 drop 에서 구해 review
g = seg(start=120, end=290, multi="watch"); g["tier"], g["tier_why"] = tier(g, True); json.dump([OK], open(f, "w")); known_pos(7, g, f); assert g["tier"] == "drop"   # 레이아웃 watch 는 승인으로도 못 뒤집음
g = seg(start=120, end=290, multi="idle"); g["tier"], g["tier_why"] = tier(g, True); known_pos(7, g, f); assert g["tier"] == "drop"
g = seg(start=120, end=290, **mv); g["tier"], g["tier_why"] = tier(g, True); known_pos(8, g, f); assert g["tier"] == "drop"      # 다른 방송
os.remove(f); print("known_pos ok")
from route import mark_likely
S = [seg(start=300 + 60 * i, tier="review", multi="live") for i in range(19)]
mark_likely(S); assert all(g["likely"] for g in S)                       # 19개: 몰림 아님
S = [seg(start=300 + 60 * i, tier="review", multi="live") for i in range(20)]
mark_likely(S); assert not any(g["likely"] for g in S)                   # 1시간 안 20개 = 의심
S = [seg(start=400, tier="review", multi="live"), seg(start=900, tier="review", multi="unknown"), seg(start=1500, tier="auto", multi="live"), seg(start=100, tier="review", multi="live"),
     seg(start=2000, tier="review", multi="live", len=100), seg(start=2500, tier="optional", multi="live")]
mark_likely(S); assert [g["likely"] for g in S] == [True, False, False, False, False, False]
print("likely ok")
# 영상 움직임(tstd): 34.5 초과는 watch 로 drop(캐시된 multi 가 live 여도), 25~34.5 는 weak(likely 제외), 25 미만은 그대로
assert tier(seg(multi="live", tstd=40), True)[0] == "drop" and tier(seg(multi="live", tstd=34.2), True)[0] == "auto" and tier(seg(multi="live", tstd=20), True)[0] == "auto"
S = [seg(start=400, tier="review", multi="live", tstd=t) for t in (10, 30, 34.5, 25, 24.9)]
mark_likely(S); assert [(g["weak"], g["likely"]) for g in S] == [(False, True), (True, False), (True, False), (True, False), (False, True)]
S = [seg(start=400, tier="review", multi="live", speech=s) for s in (0.05, 0.06)]
mark_likely(S); assert [g["likely"] for g in S] == [True, False]                  # 멘트 섞인 배경 노래는 유력 제외
print("motion ok")
# 승인 경계가 곡의 정답이 아닌 B(boundary_ok=False)는 겹쳐도 auto 로 올리지 않는다
f = tempfile.mktemp(suffix=".json"); json.dump([dict(videoNo="s_1", start=100, end=300, src="t", boundary_ok=False)], open(f, "w"))
g = seg(start=102, end=298, tier="review"); known_pos("s_1", g, f); assert g["tier"] == "review" and "경계 문제" in g["tier_why"] and "ref_bd" not in g
os.remove(f); print("boundary_ok ok")
