"""치지직 카테고리 -> 곡 클립 사전확률 (권고용; route.py 는 건드리지 않음). 근거 수치는 cache/exp12_cat_eval.json.
shortcut: 표본이 작아(재생목록 정답 있는 날 약 30방송) 보정값은 보수적 상수, 표본이 늘면 experiments/exp12_cat_eval.py 로 갱신."""
import math


def wilson(h, n, z=1.96):
    if n == 0:
        return [0.0, 1.0]
    p = h / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round((c - w) / d, 3), round((c + w) / d, 3)]


def group(category):
    return "music" if category == "음악/노래" else ("talk" if category in ("talk", "") else "game")


# 로그 오즈 보정. 값은 exp12_cat_eval 결과를 본 뒤 채움(기본 0 = 영향 없음).
PRIOR = {"music": 0.0, "talk": 0.0, "game": 0.0}


def prior(category):
    return PRIOR[group(category)]


if __name__ == "__main__":
    assert wilson(0, 0) == [0.0, 1.0] and wilson(5, 10)[0] < 0.5 < wilson(5, 10)[1]
    assert group("음악/노래") == "music" and group("리그 오브 레전드") == "game" and group("talk") == "talk"
    print("ok")
