"""화면 의미로 N(라이브 아님)을 가르는 신호 (등록부 없음). 곡 구간에서 프레임 8장 -> SigLIP2 B/16 제로샷으로 5개 프롬프트 세트마다 (N 개념 최대 유사도 - 라이브 개념 최대 유사도)의 프레임 max
-> 세트별 z 정규화(n_visual_cal.json) -> 평균 = 점수 vis (클수록 N 같음: 웹/다른 영상 창, 3D 게임, 리듬게임, 게임 OST, 콘서트/커버 영상, GTA 노래방).
  fire(g) : vis 가 임계 초과이면 사유 목록(없으면 None = 판단 불가, 빈 목록 = 통과). route.mark_likely 가 n_signals 와 같은 방식으로 weak 표시에 쓴다(drop 아님: 게임 화면 속 진짜 라이브가 있다).
  fill(segs, src) : keep 후보에 g['vis'] 를 채운다(프레임은 ffmpeg 로 구간 8등분 중앙 시각). 모델 로딩 약 10초 + 곡당 약 0.1초(GPU). 프레임을 못 읽으면 건드리지 않는다(= 옛 동작).
임계 근거(experiments_log/visual.md): 스트리머 단위 hold-out 에서 임계 = 학습 라이브 점수 최댓값 + 0.1 x 범위 일 때 N 37/71 거름 + 라이브 손실 0/133(m=0 이면 GTA 안 라이브 1곡 손실). n_visual_cal.json 의 thr 은 전체 표본(라이브 133곡)에 같은 식을 적용한 값이다.
shortcut: (1) 모델 선택(SigLIP2 B/16 단독)은 4모델 비교를 본 뒤 고른 것이라 선택 편향이 있다(선택 없는 4모델 평균은 N 22/71, 손실 0). (2) 라이브가 스트리머 11명 표본(2명이 절반)이라 새 스트리머에서 라이브가 걸릴 수 있다(걸려도 weak 표시일 뿐 drop 아님).
(3) 같은 날 같은 GTA 장면의 라이브(리제 10-03 #14648)는 화면으로 못 가른다 -> 반드시 weak/우선순위로만 쓰고 단독 drop 금지.
사용: python n_visual.py (자가검사)"""
import json, os, subprocess
from pathlib import Path

CAL = Path(__file__).parent / "n_visual_cal.json"
MODEL = ("ViT-B-16-SigLIP2", "webli")
NF = 8                                                       # 곡당 프레임 수 (1장 AUC 0.870 -> 8장 0.881 이라 4장도 가능)
SETS = {
    "A_basic": dict(N=["a screenshot of a web browser page", "a 3D video game scene", "a rhythm game with falling notes", "a concert video playing on screen", "a static waiting screen with text", "a YouTube video player", "a split screen showing another streamer's broadcast"],
                    L=["an anime virtual avatar singing into a microphone", "a close-up of a virtual youtuber avatar"]),
    "B_desc": dict(N=["a desktop screenshot with a web page and a small virtual avatar at the corner", "a first person video game with a small avatar overlay in the corner", "a karaoke room inside a 3D open world game",
                      "a music video or concert footage shown in a window", "a rhythm game screen with note lanes and a score", "a still image with a be right back message", "a video of another streamer playing in a window next to the avatar", "a music player showing album art and a song title"],
                   L=["a large anime avatar face filling the screen with a chat overlay", "a vtuber avatar standing on a stage with a microphone and lyrics", "a virtual singer performing a live song on stream"]),
    "C_game": dict(N=["video game", "game user interface with a minimap", "gameplay footage", "web browser", "website", "video player controls", "music game", "concert"], L=["anime girl avatar", "virtual streamer", "character illustration", "singing"]),
    "D_only_N": dict(N=["a screenshot of a web browser page", "a 3D video game scene", "a rhythm game with falling notes", "a concert video playing on screen", "a YouTube video player", "a split screen showing another streamer's broadcast", "a static waiting screen with text"], L=["a photo"]),
    "E_layout": dict(N=["a screen with a large video window and a small avatar in the corner", "a screen with two video windows side by side", "a dark game screen with a heads-up display", "a screen with a webpage and text columns"],
                     L=["a screen mostly filled by a single large anime character", "a colorful stage background behind an anime character"]),
}
_M = {}


def cal():
    return json.load(open(CAL, encoding="utf8"))


def _load():
    if not _M:
        import torch, open_clip
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        m, _, pre = open_clip.create_model_and_transforms(*MODEL)
        m = m.to(dev).eval().half() if dev == "cuda" else m.to(dev).eval()
        tok = open_clip.get_tokenizer(MODEL[0])
        norm = next(t for t in pre.transforms if t.__class__.__name__ == "Normalize")
        enc = lambda ts: torch.nn.functional.normalize(m.encode_text(tok(ts).to(dev)).float(), dim=-1)
        with torch.no_grad():
            T = {k: (enc(v["N"]), enc(v["L"])) for k, v in SETS.items()}
        S = m.visual.image_size[0] if isinstance(m.visual.image_size, (tuple, list)) else m.visual.image_size
        _M.update(m=m, norm=norm, T=T, S=S, dev=dev)
    return _M


def components(imgs):
    """PIL 이미지 목록 -> 세트별 프레임 max (N 개념 - 라이브 개념 코사인 차) 5개. 프레임 전체를 정사각형으로 찌그러뜨려 넣는다(레이아웃 보존)"""
    import numpy as np, torch
    from PIL import Image
    M = _load()
    x = torch.stack([M["norm"](torch.from_numpy(np.asarray(im.convert("RGB").resize((M["S"], M["S"]), Image.BICUBIC)).copy()).permute(2, 0, 1).float() / 255) for im in imgs]).to(M["dev"])
    x = x.half() if M["dev"] == "cuda" else x
    with torch.no_grad():
        e = torch.nn.functional.normalize(M["m"].encode_image(x).float(), dim=-1)
        return [float(((e @ tn.T).max(1).values - (e @ tl.T).max(1).values).max()) for tn, tl in M["T"].values()]


def vis_of(comps, c=None):
    c = c or cal()
    return sum((v - mu) / sd for v, mu, sd in zip(comps, c["mu"], c["sd"])) / len(comps)


def frames_of(src, s, e, n=NF):
    """구간 [s,e] 를 n 등분한 중앙 시각의 프레임 n장(PIL, 398x224). NAS 주소는 세션 쿠키로 읽는다. 실패한 프레임은 건너뜀"""
    import io
    from PIL import Image
    import nas_auth
    out = []
    for i in range(n):
        t = s + (e - s) * (i + 0.5) / n
        try:
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", *nas_auth.ffargs(src), "-i", str(src), "-frames:v", "1", "-vf", "scale=398:224", "-f", "image2pipe", "-vcodec", "mjpeg", "-"],
                                 capture_output=True, check=True, timeout=120, creationflags=0x4000 if os.name == "nt" else 0).stdout
            out.append(Image.open(io.BytesIO(raw)).convert("RGB"))
        except Exception:
            pass
    return out


def fill(segs, src):
    """keep 후보 중 g['vis'] 가 없는 것에 채운다. 프레임이 3장 미만이면 건드리지 않는다(fire 가 None)"""
    if not CAL.exists():
        return
    c = cal()
    for g in segs:
        if g.get("keep") and g.get("vis") is None:
            im = frames_of(src, g["start"], g["end"])
            if len(im) >= 3:
                g["vis"] = vis_of(components(im), c)


def fire(g, c=None):
    """사유 목록 (vis 없음 = None, 임계 이하 = 빈 목록)"""
    if g.get("vis") is None or not CAL.exists():
        return None
    thr = (c or cal())["thr"]
    return [f"화면이 라이브 노래 장면과 다름(vis {g['vis']:.2f} > {thr:.2f}: 웹/영상 창/게임/리듬게임/공연 영상)"] if g["vis"] > thr else []


if __name__ == "__main__":
    assert fire({}) is None
    if CAL.exists():
        c = cal()
        assert fire({"vis": c["thr"] + 0.01}, c) and fire({"vis": c["thr"]}, c) == [] and fire({"vis": None}, c) is None
        assert abs(vis_of(c["mu"], c)) < 1e-9                       # 평균 입력 -> 점수 0
    print("ok")
