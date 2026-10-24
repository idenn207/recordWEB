"""python test_route.py"""
from route import tier

seg = lambda **k: {"keep": True, "len": 200, "scene": 0.04, **k}
assert tier(seg(), True)[0] == "auto"
assert tier(seg(keep=False, why="short"), True) == ("drop", "short")
assert tier(seg(scene=0.30), True)[0] == "drop"            # 같이 보기/영상 시청 화면
assert tier(seg(scene=0.30), False)[0] == "review"         # 새 채널은 기준이 없어 판단 보류
assert tier(seg(scene=0.10), True)[0] == "review"          # 애매한 장면(콘서트 0.08~0.12 대)
assert tier(seg(scene=None), True)[0] == "review"          # 장면을 못 읽으면 통과시키지 않는다
assert tier(seg(len=100), True)[0] == "review"             # 1절 또는 짧은 랩
assert tier(seg(len=400), True)[0] == "review"             # 곡 합쳐짐 의심
print("ok")
