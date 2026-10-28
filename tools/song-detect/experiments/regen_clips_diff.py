"""재생성 전/후 완곡 클립 비교(파일 기준): out/stale_v5/{final,final_review}(전) 대 out/{final,final_review}(후)를 (방송, 카드번호)로 묶어 곡 경계/컷/클립 길이 변화와 승인 L(boundary_ok) 여부를 낸다.
사용: python experiments/regen_clips_diff.py [--all]   (기본: 변화가 있는 곡만)
      python experiments/regen_clips_diff.py --archive   (같은 카드의 클립이 out/final* 에 둘 이상이면(컷이 바뀌어 파일 이름이 달라진 재생성) 오래된 것을 out/stale_v5/iter1/ 로 옮긴다, 삭제 안 함)"""
import glob, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent


def load(base):
    out = {}
    for f in glob.glob(str(ROOT / base / "*/*.json")):
        if f.endswith("_ctx20.json"):
            continue
        j = json.load(open(f, encoding="utf8"))
        out[("_".join(Path(f).parent.name.split("_")[2:]), j["card_idx"])] = j
    return out


def archive():
    import os, shutil
    G = {}
    for t in ("final", "final_review"):
        for f in glob.glob(str(ROOT / "out" / t / "*/*.json")):
            if not f.endswith("_ctx20.json"):
                G.setdefault((t, os.path.dirname(f), json.load(open(f, encoding="utf8"))["card_idx"]), []).append((os.path.getmtime(f), f))
    n = 0
    for (t, d, _), v in G.items():
        for _, f in sorted(v)[:-1]:
            dest = ROOT / "out/stale_v5/iter1" / t / Path(d).name; dest.mkdir(parents=True, exist_ok=True)
            for ext in (".json", ".mp4", "_ctx20.mp4"):
                if os.path.exists(f[:-5] + ext):
                    shutil.move(f[:-5] + ext, dest); n += 1
    print("옮긴 파일", n)


if __name__ == "__main__":
    if "--archive" in sys.argv:
        archive(); sys.exit()
    A = {**load("out/stale_v5/final"), **load("out/stale_v5/final_review")}
    B = {**load("out/final"), **load("out/final_review")}
    only_a, only_b = sorted(set(A) - set(B)), sorted(set(B) - set(A))
    print(f"전 {len(A)}곡, 후 {len(B)}곡, 전에만 {only_a}, 후에만 {only_b}")
    n = mx = 0
    for k in sorted(set(A) & set(B)):
        a, b = A[k], B[k]
        d = dict(s=b["song_start"] - a["song_start"], e=b["song_end"] - a["song_end"], cs=b["vod_start"] - a["vod_start"], ce=b["vod_end"] - a["vod_end"], L=b["clip_len"] - a["clip_len"])
        mx = max(mx, abs(d["L"]))
        if "--all" in sys.argv or any(abs(v) > 0.05 for v in d.values()) or a["tier"] != b["tier"]:
            n += 1
            print(f"{k[0]} #{k[1]:02d} {a['tier']:6s}->{b['tier']:6s} 곡 시작 {d['s']:+.2f} 끝 {d['e']:+.2f} | 컷 시작 {d['cs']:+.2f} 끝 {d['ce']:+.2f} | 클립 길이 {d['L']:+.2f}  ok {a['ok']}->{b['ok']}")
    print(f"변화 {n}곡, 클립 길이 최대 |변화| {mx:.2f}초, 모든 클립 ok: {all(j['ok'] for j in B.values())}, 리미터 켜진 클립 {sum(1 for j in B.values() if j['limiter'])}")
