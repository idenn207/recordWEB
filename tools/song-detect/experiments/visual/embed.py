"""visual 트랙 3단계: 프레임 임베딩 캐시. 모델마다 cache/proto_visual/emb_<이름>_<모드>.npz = {key: (8, D) L2 정규화}.
모드 squash = 16:9 프레임 전체를 정사각형으로 찌그러뜨림(레이아웃 보존), crop = 중앙 정사각형 크롭(CLIP 기본), lowres = 144p 로 줄였다 늘린 뒤 squash(해상도 출처 누수 제거).
사용: python experiments/visual/embed.py <모델별칭> [모드]   별칭: b32 l14 sigb16 sig2b16 sigso400"""
import json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
import numpy as np, torch, open_clip
from PIL import Image

MODELS = {"b32": ("ViT-B-32", "openai"), "l14": ("ViT-L-14", "openai"), "sigb16": ("ViT-B-16-SigLIP", "webli"), "sig2b16": ("ViT-B-16-SigLIP2", "webli"),
          "sig2b32": ("ViT-B-32-SigLIP2-256", "webli"), "sigso400": ("ViT-SO400M-14-SigLIP", "webli")}
FR = Path("cache/proto_visual/frames")


def load(alias, dev="cuda"):
    n, p = MODELS[alias]
    m, _, pre = open_clip.create_model_and_transforms(n, pretrained=p)
    return m.to(dev).eval().half(), pre, open_clip.get_tokenizer(n)


def prep(im, S, mode, norm):
    if mode == "lowres":
        im = im.resize((256, 144), Image.BILINEAR).resize((398, 224), Image.BILINEAR)
    if mode == "crop":
        w, h = im.size; x = (w - h) // 2; im = im.crop((x, 0, x + h, h)).resize((S, S), Image.BICUBIC)
    else:
        im = im.resize((S, S), Image.BICUBIC)
    return norm(torch.from_numpy(np.asarray(im).copy()).permute(2, 0, 1).float() / 255)


def main(alias, mode="squash", bs=32):
    out = Path(f"cache/proto_visual/emb_{alias}_{mode}.npz")
    m, pre, _ = load(alias)
    S = m.visual.image_size[0] if isinstance(m.visual.image_size, (tuple, list)) else m.visual.image_size
    norm = next(t for t in pre.transforms if t.__class__.__name__ == "Normalize")
    keys = [r["key"] for r in json.load(open("cache/proto_visual/manifest.json", encoding="utf8"))]
    res, t0 = {}, time.time()
    for k in keys:
        fs = sorted((FR / k.replace("/", "__")).glob("*.jpg"), key=lambda p: int(p.stem))
        if len(fs) < 3:
            continue
        x = torch.stack([prep(Image.open(f).convert("RGB"), S, mode, norm) for f in fs]).cuda().half()
        with torch.no_grad():
            e = m.encode_image(x).float()
        res[k] = torch.nn.functional.normalize(e, dim=-1).cpu().numpy()
    np.savez_compressed(out, **{k.replace("/", "|"): v for k, v in res.items()})
    n = sum(len(v) for v in res.values())
    print(alias, mode, len(res), "곡", n, "장", f"{time.time()-t0:.1f}s", f"{(time.time()-t0)/max(n,1)*1000:.1f}ms/장", f"VRAM최대 {torch.cuda.max_memory_allocated()/2**30:.2f}GB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "squash")
