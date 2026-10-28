"""경쟁 측정: 지금 이 PC 에서 내가 실제로 쓸 수 있는 병렬도(5개 트랙이 같은 CPU 를 씀). 고정 CPU 작업(약 80ms)을 N 프로세스로 돌려 처리량 배율을 잼. 서비스 처리량을 보정하는 데 쓴다."""
import multiprocessing as mp, time, sys

def spin(_):
    t = time.perf_counter(); x = 0
    for i in range(1_200_000):
        x += i * i
    return time.perf_counter() - t

if __name__ == "__main__":
    base = spin(0)
    out = {}
    for n in (1, 4, 8, 16, 20):
        with mp.Pool(n) as p:
            p.map(spin, range(n))
            t = time.perf_counter(); p.map(spin, range(n * 6)); dt = time.perf_counter() - t
        out[n] = round(n * 6 * base / dt, 1)
    print("단독 1회", round(base * 1000), "ms | 프로세스 수 -> 유효 병렬도(이상적이면 n):", out)
