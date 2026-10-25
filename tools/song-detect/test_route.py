"""python test_route.py"""
from route import tier

seg = lambda **k: {"keep": True, "len": 200, "scene": 0.04, **k}
assert tier(seg(), True)[0] == "auto"
assert tier(seg(keep=False, why="short"), True) == ("drop", "short")
assert tier(seg(piano=True), False)[0] == "drop" and tier(seg(piano=False), True)[0] == "auto"   # piano_gate 표시가 있을 때만 drop
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
print("pool ok")
