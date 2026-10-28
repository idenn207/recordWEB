"""other_live_watch(타 스트리머 방송 같이 보기, 12곡) 전용 프롬프트 시험 (E): 라이브(133) 대비 이 유형의 AUROC 와 hold-out veto. python run_other.py"""
import warnings; warnings.filterwarnings("ignore")
import torch
from evlib import *
from embed import load
SETS = {
 "F_two": dict(N=["two different anime characters on screen", "a small window showing another vtuber's live stream", "a streamer reacting to another streamer's broadcast"], L=["a single anime character"]),
 "G_ui": dict(N=["a video window with a play bar and a chat panel", "a screenshot of a live streaming website", "a picture in picture video overlay"], L=["a vtuber avatar overlay with a chat window"]),
 "H_song": dict(N=["a lyric video with a song title and artist name in the corner", "a music streaming now playing label", "a karaoke video with lyrics at the bottom"], L=["an anime avatar singing"]),
}
for a in ("sig2b16", "l14"):
    df, E = dataset(a); m, _, tok = load(a)
    y = (df.live == 0).to_numpy(); ow = (df.tag == "other_live_watch").to_numpy(); live = ~y
    for sn, st in SETS.items():
        with torch.no_grad():
            tn, tl = [torch.nn.functional.normalize(m.encode_text(tok(t).cuda()).float(), dim=-1).cpu().numpy() for t in (st["N"], st["L"])]
        s = ((E @ tn.T).max(2) - (E @ tl.T).max(2)).max(1)
        r = veto(df, lambda tr, te: (s[tr], s[te]), "streamer", ms=(0.0, 0.1))
        print(f"{a} {sn}: other_live_watch vs 라이브 AUC {auc(s[ow], s[live]):.3f} | 전체 N AUC {r['auc']:.3f} | m=0.1 거름 other {r['hit0.1'][ow].sum()}/12 전체 N {r['hit0.1'][y].sum()}/71 라이브 손실 {r['hit0.1'][live].sum()}")
