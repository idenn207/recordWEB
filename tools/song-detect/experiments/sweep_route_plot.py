"""route 탐색 결과 그림: OAT 곡선, 2D 격자(라이브 손실 있는 칸은 빗금), 탐색기 비교, 파레토(Sobol 1M). 출력 cache/proto_sweep/route_*.png"""
import json, sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False
O = Path("cache/proto_sweep")


def oat():
    r = json.load(open(O / "route_oat.json"))
    fig, ax = plt.subplots(3, 5, figsize=(22, 11))
    for a, (k, d) in zip(ax.flat, r.items()):
        v = np.array(d["v"])
        a.plot(v, d["N_all"], "b-", label="N 노출(75)")
        a.plot(v, np.array(d["L_loss"]), "r-", label="라이브 손실(136)")
        a.plot(v, np.array(d["N_auto"]), "m--", label="N auto")
        a2 = a.twinx(); a2.plot(v, d["L_auto"], "g:", label="auto 라이브")
        a.axvline(d["default"], color="gray", ls="--")
        a.set_title(k)
        a.set_ylim(-1, 40)
    ax.flat[0].legend(fontsize=8)
    plt.tight_layout(); plt.savefig(O / "route_oat.png", dpi=65); plt.close()


def grids():
    G = json.load(open(O / "route_grid.json"))
    fig, ax = plt.subplots(2, 3, figsize=(18, 11))
    for a, (k, g) in zip(ax.flat, G.items()):
        N = np.array(g["N_all"], float); L = np.array(g["L_loss"]); A = np.array(g["N_auto"])
        bad = (L > 0) | (A > 0)
        im = a.imshow(np.where(bad, np.nan, N).T, origin="lower", aspect="auto", extent=[g["va"][0], g["va"][-1], g["vb"][0], g["vb"][-1]], cmap="viridis_r")
        a.imshow(np.where(bad, 1.0, np.nan).T, origin="lower", aspect="auto", extent=[g["va"][0], g["va"][-1], g["vb"][0], g["vb"][-1]], cmap="Greys", alpha=0.6, vmin=0, vmax=2)
        a.set_xlabel(g["a"]); a.set_ylabel(g["b"]); a.set_title(f"N 노출(회색 = 라이브 손실 또는 N auto)")
        d = __import__("sweep_route").DEF
        a.plot([d[g["a"]]], [d[g["b"]]], "r*", ms=14)
        plt.colorbar(im, ax=a)
    plt.tight_layout(); plt.savefig(O / "route_grid.png", dpi=65); plt.close()


def optim():
    r = json.load(open(O / "route_optuna.json"))
    fig, a = plt.subplots(figsize=(9, 6))
    for k, cs in r.items():
        for i, c in enumerate(cs):
            c = np.array([x if x < 1e9 else np.nan for x in c], float)
            a.plot(c, color={"random": "gray", "sobol": "k", "tpe": "b", "cmaes": "r", "nsga2": "g"}[k], alpha=.7, label=k if i == 0 else None)
    a.axhline(15, color="orange", ls="--", label="현재 설정 N=15"); a.set_xscale("log"); a.set_xlabel("시험 횟수"); a.set_ylabel("제약 만족 설정의 최소 N 노출"); a.legend()
    plt.tight_layout(); plt.savefig(O / "route_optim.png", dpi=70); plt.close()


def pareto():
    z = np.load(O / "route_random.npz")
    L, N, A, LA = z["m_L_loss"], z["m_N_all"], z["m_N_auto"], z["m_L_auto"]
    ok = (L == 0) & (A == 0)
    fig, ax = plt.subplots(1, 2, figsize=(15, 6))
    ax[0].scatter(N[ok] + np.random.default_rng(0).uniform(-.3, .3, ok.sum()), LA[ok] + np.random.default_rng(1).uniform(-.3, .3, ok.sum()), s=3, alpha=.25, c="gray", label=f"제약 만족 {ok.sum()}개 (Sobol 1M 중)")
    pts = sorted(set(zip(N[ok].tolist(), LA[ok].tolist())))
    front, best = [], -1
    for n, la in sorted(pts, key=lambda p: (p[0], -p[1])):
        if la > best:
            front.append((n, la)); best = la
    ax[0].plot(*zip(*front), "r-o", label="파레토(N 노출 최소, auto 라이브 최대)")
    ax[0].plot([15], [13], "c*", ms=18, label="현재 설정")
    ax[0].set_xlabel("N 노출(75행)"); ax[0].set_ylabel("auto 로 나간 라이브(136행)"); ax[0].legend(); ax[0].set_title("라이브 손실 0, N auto 0 인 설정들")
    json.dump(front, open(O / "route_pareto_front.json", "w"))
    ax[1].scatter(N[::5], L[::5] + 0.0, s=2, c="k", alpha=.15)
    ax[1].set_yscale("symlog"); ax[1].set_xlabel("N 노출(75)"); ax[1].set_ylabel("라이브 손실(136)"); ax[1].set_title("전체 Sobol 설정(5개 중 1개): 손실 0 을 지키면서 N 을 줄이는 한계")
    plt.tight_layout(); plt.savefig(O / "route_pareto.png", dpi=65); plt.close()
    print("front", front)


if __name__ == "__main__":
    sys.path.insert(0, "experiments")
    oat(); grids(); optim(); pareto(); print("ok")
