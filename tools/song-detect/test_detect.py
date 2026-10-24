"""도커에서: docker run --rm --entrypoint python -v "$PWD/test_detect.py:/work/test_detect.py" -v "$PWD/detect.py:/work/detect.py" song-detect test_detect.py"""
import numpy as np
from detect import walk, extend, split_at_talk, HOP

m = np.zeros(400); m[100:300] = 0.9                        # 음악 50~150초
assert walk(m, 100, -1, 60) == 50                          # 음악이 시작되는 곳까지 되돌아간다
assert walk(m, 100, -1, 20) == 80                          # 상한(cap)에서 멈춘다
m[180:184] = 0.1                                           # 2초 틈은 곡 안의 쉼으로 보고 건너뛴다
assert walk(m, 80, +1, 120) == 149.5
m[180:200] = 0.1                                           # 10초 틈은 곡 경계
assert walk(m, 80, +1, 120) == 89.5
a = np.zeros((400, 3)); a[100:300, 2] = 0.9
s, e = extend(a, 70, 140)
assert abs(s - 50) < 1.5 and abs(e - 151) < 1.5, (s, e)
sung = np.array([1]*12 + [0, 0, 0] + [1]*12, bool)       # 5초 창: 노래 60초, 15초 비노래, 노래 60초
talk = np.zeros(27, bool)
assert split_at_talk([(0, 135)], sung, talk, 5, 10) == [(0, 135)]                # 말소리 없는 쉼(간주)은 나누지 않는다
talk[13] = True
assert split_at_talk([(0, 135)], sung, talk, 5, 10) == [(0, 60), (75, 135)]      # 말소리가 낀 10초 이상 블록에서 나눈다
assert split_at_talk([(0, 135)], sung, np.r_[talk[:13], True, talk[14:]], 5, 20) == [(0, 135)]  # 블록이 min_s 보다 짧으면 나누지 않는다
print("ok")
