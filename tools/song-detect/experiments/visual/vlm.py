"""소형 VLM 질의 (E16~): 프레임마다 예/아니오 질문의 logit(Yes)-logit(No) 를 점수로 cache/proto_visual/vlm_<모델>.npz 에 저장. python vlm.py <smol500|smol256|qwen2vl> [프레임수=4]
질문은 N 유형 6가지에 대응. 비용(곡당 초)과 VRAM 최대를 출력한다."""
import json, os, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; os.chdir(ROOT)
import numpy as np, torch
from PIL import Image
from transformers import AutoProcessor, AutoModelForImageTextToText

REPO = {"smol500": "HuggingFaceTB/SmolVLM-500M-Instruct", "smol256": "HuggingFaceTB/SmolVLM-256M-Instruct", "qwen2vl": "Qwen/Qwen2-VL-2B-Instruct"}
Q = {"web_or_video": "Is there a web browser page or another video player window shown on the screen? Answer yes or no.",
     "game_scene": "Is this a video game scene with a 3D world or game interface? Answer yes or no.",
     "mic_avatar": "Is the cartoon character holding a microphone? Answer yes or no.",
     "big_avatar": "Is the screen mostly filled by one large anime character? Answer yes or no.",
     "other_streamer": "Does the screen show a second person or character from another stream in a window? Answer yes or no.",
     "static_text": "Is this a still waiting screen with text or a logo? Answer yes or no."}
FR = Path("cache/proto_visual/frames")


def main(name, nf=4):
    proc = AutoProcessor.from_pretrained(REPO[name], do_image_splitting=False)
    model = AutoModelForImageTextToText.from_pretrained(REPO[name], torch_dtype=torch.float16).cuda().eval()
    tk = proc.tokenizer
    yes = [tk.encode(w, add_special_tokens=False)[0] for w in ("Yes", " Yes", "yes")]
    no = [tk.encode(w, add_special_tokens=False)[0] for w in ("No", " No", "no")]
    rows = json.load(open("cache/proto_visual/manifest.json", encoding="utf8"))
    out, t0 = {}, time.time()
    sel = np.linspace(0, 7, nf).round().astype(int)
    for r in rows:
        d = FR / r["key"].replace("/", "__")
        fs = [d / f"{i}.jpg" for i in sel if (d / f"{i}.jpg").exists()]
        if len(fs) < nf:
            continue
        sc = np.zeros((len(Q), len(fs)), np.float32)
        for qi, q in enumerate(Q.values()):
            for fi, f in enumerate(fs):
                msgs = [{"role": "user", "content": [{"type": "image"}, {"type": "text", "text": q}]}]
                prompt = proc.apply_chat_template(msgs, add_generation_prompt=True)
                inp = proc(text=prompt, images=[Image.open(f).convert("RGB")], return_tensors="pt").to("cuda")
                inp = {k: (v.half() if v.dtype == torch.float32 else v) for k, v in inp.items()}
                with torch.no_grad():
                    lg = model(**inp).logits[0, -1].float()
                sc[qi, fi] = (torch.logsumexp(lg[yes], 0) - torch.logsumexp(lg[no], 0)).item()
        out[r["key"].replace("/", "|")] = sc
        if len(out) % 5 == 0:
            print(len(out), f"{time.time()-t0:.0f}s", flush=True)
    np.savez_compressed(f"cache/proto_visual/vlm_{name}.npz", **out)
    dt = time.time() - t0
    print(name, len(out), "곡", f"{dt:.0f}s", f"곡당 {dt/len(out):.1f}s (프레임 {nf}장 x 질문 {len(Q)}개)", f"VRAM최대 {torch.cuda.max_memory_allocated()/2**30:.2f}GB")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 4)
