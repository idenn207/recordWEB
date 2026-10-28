"""작업대 보조: 메모 곡(gid)의 현재 곡 경계 주변 신호 타임라인(텍스트). python experiments/bl_view.py <gid> [start|end] [창초]"""
import sys; sys.path.insert(0, 'experiments')
from bound_lab import *
import audit_engine as E
from snap import rms_db, HOP

def cand(gid):
    exp = M.jl(M.EXP); g = next(g for g in exp["groups"] if g["gid"] == gid)
    for c in E.kept(g["vno"]):
        o = E.calc(g["vno"], c["start"], c["end"])
        if M.ov(o["song_s"], o["song_e"], *g["base"]) > 0.5 * (g["base"][1] - g["base"][0]):
            return g, c, o
def line(pcm, a, voc, t, w=1.0):
    ts, db = rms_db(pcm, t, t + w)
    k = int(t / HOP)
    s = snap.vwin(voc, a, t)
    return f"{t:9.1f} dB {np.median(db):6.1f} Si {a[k:k+int(w/HOP),0].mean():.2f} Sp {a[k:k+int(w/HOP),1].mean():.2f} Mu {a[k:k+int(w/HOP),2].mean():.2f} voc {s[0] if s else float('nan'):.2f}"
if __name__ == "__main__":
    gid = int(sys.argv[1]); side = sys.argv[2] if len(sys.argv) > 2 else "start"; W = float(sys.argv[3]) if len(sys.argv) > 3 else 40
    g, c, o = cand(gid)
    pcm, a, voc = E.wdata(g["vno"])
    ref = float(np.median(rms_db(pcm, o["song_s"], o["song_e"])[1]))
    t0 = o["song_s"] if side == "start" else o["song_e"]
    tr = g["sides"][side]["truth"]
    print(f"#{gid} {g['slug'][-24:]} refine {c['start']:.1f}-{c['end']:.1f} song {o['song_s']:.1f}-{o['song_e']:.1f} ({o['song_e']-o['song_s']:.0f}s) ref {ref:.1f}dB truth {tr} issue {g['sides'][side]['issue']} rules {[(x['rule'],x['edge'],x['shift']) for x in o['stages']]}")
    print(g["memo"][:200])
    step = 2.0
    for t in np.arange(t0 - W, t0 + W / 2, step):
        mark = " <== " + side if abs(t - t0) < step / 2 else (" <== truth" if tr and abs(t - tr) < step / 2 else "")
        print(line(pcm, a, voc, t, step) + mark)
