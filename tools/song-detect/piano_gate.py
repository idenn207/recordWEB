"""피아노 연주 의심 게이트: 보컬 스템 비율이 낮고 Demucs 'other' 스템(피아노가 여기로 감) 비율이 높으면 가창이 아닌 연주로 본다.
피아노 치며 노래하는 라이브는 보컬 스템 비율이 높아(0.55 이상) 걸리지 않는다. g['vocal'] 은 detect 가 이미 계산한 값을 쓰고, 새로 필요한 것은 other 비율뿐.
사용: docker(GPU)에서 `python piano_gate.py scan <videoNo>...` -> cache/exp12p/other.json({videoNo:{start:other}}), 호스트에서 annotate(vid, segs) 가 g['other'], g['piano'] 를 채우고 route.tier 가 읽는다.
  python piano_gate.py selftest
shortcut: 임계값은 히나 41개 표본(귀로 확인 못 함, other 비율 0.36~0.47 사이가 비어 있음)으로 정함. 다른 스트리머/BGM 있는 게임 방송에서 오탐 가능 -> 표본이 쌓이면 재보정"""
import json, sys
from pathlib import Path

P = dict(vocal_max=0.5, other_min=0.45)
F = Path("cache/exp12p/other.json")


def suspect(vocal, other, p=P):
    return other is not None and vocal is not None and vocal < p["vocal_max"] and other >= p["other_min"]


def annotate(vid, segs, path=F):
    """cache 에 other 가 있는 후보만 표시한다(없으면 아무것도 안 함 = 기존 동작 그대로)."""
    if not Path(path).exists():
        return
    o = json.load(open(path, encoding="utf8")).get(str(vid), {})
    for g in segs:
        x = o.get(str(round(g["start"])))
        if x is not None:
            g["other"], g["piano"] = x, suspect(g.get("vocal"), x)


def scan(vids):
    import numpy as np, torch, torchaudio
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    m = get_model("htdemucs").eval().cuda()
    S = m.sources
    out = json.load(open(F, encoding="utf8")) if F.exists() else {}
    for vid in vids:
        wav = f"/work/data/vod/{vid}.wav"
        pcm = np.memmap(wav, dtype="<i2", mode="r", offset=open(wav, "rb").read(4096).find(b"data") + 8)
        res = out.setdefault(str(vid), {})
        for g in json.load(open(f"/work/out/{vid}/3_final.json", encoding="utf8")):
            if not g["keep"] or str(round(g["start"])) in res:
                continue
            o = tot = 0.0
            t, e = g["start"], min(g["end"], len(pcm) / 16000)
            while t < e:
                te = min(e, t + 60)
                x = torch.from_numpy(pcm[int(t * 16000):int(te * 16000)].astype(np.float32) / 32768)
                x = torchaudio.functional.resample(x, 16000, 44100)[None].repeat(2, 1)
                with torch.no_grad():
                    y = apply_model(m, x[None], device="cuda")[0].cpu()
                o += float(y[S.index("other")].pow(2).sum()); tot += float(x.pow(2).sum()); t = te
            res[str(round(g["start"]))] = round(o / (tot + 1e-9), 3)
        F.write_text(json.dumps(out), encoding="utf8")


def selftest():
    assert suspect(0.31, 0.63) and suspect(0.46, 0.61)
    assert not suspect(0.73, 0.03)              # 일반 라이브
    assert not suspect(0.55, 0.60)              # 피아노 치며 노래(보컬 스템 높음)
    assert not suspect(0.3, 0.1) and not suspect(None, 0.9) and not suspect(0.3, None)   # 단순 BGM/대기 화면, 값 없음은 건드리지 않음
    g = [dict(start=100.2, vocal=0.3)]
    annotate("x", g, path="nonexistent.json"); assert "piano" not in g[0]
    print("selftest ok")


if __name__ == "__main__":
    selftest() if sys.argv[1:2] == ["selftest"] else scan(sys.argv[2:])
