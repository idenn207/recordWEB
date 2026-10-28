"""얇은 상수 오버라이드 장치 (sweep 트랙): 코드는 그대로 두고 모듈 상수/딕셔너리 항목/함수 기본 인자를 이름으로 바꿔 실험한다.
키 형식 (점으로 구분):
  snap.LOW                 모듈 상수            -> snap.LOW = 값
  detect.P.gap_s           모듈의 딕셔너리 항목 -> detect.P["gap_s"] = 값   (route.P, scene_multi.P, n_signals.P 도 같다)
  snap.deep_end.depth      함수 기본 인자       -> snap.deep_end 의 depth 기본값 (키워드 기본값/위치 기본값 모두)
  refine.refine.bias_start 함수 기본 인자 (refine 의 bias_start/bias_end)
사용:
  import tune; undo = tune.apply({"snap.LOW": 0.3, "route.P.scene_ok": 0.08}); ...; undo()
  환경변수 SONG_TUNE='{"snap.LOW":0.3}' 또는 SONG_TUNE=@파일.json 이 있으면 `import tune` 하는 순간 적용된다(프로그램 시작 때 한 번, 되돌리지 않음).
  python tune.py list            바꿀 수 있는 이름과 현재 값 목록
주의: `from snap import LOW` 처럼 값을 복사해 간 곳은 못 바꾼다(이 저장소는 모듈 전역 참조라 해당 없음). 프로세스당 한 번 적용이 원칙이고, 되돌리려면 apply 가 준 undo 를 부른다.
shortcut: 값 검증은 타입(기존 값과 int/float 호환)만 본다. 범위 검증은 호출하는 실험 쪽 책임."""
import importlib, inspect, json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
MODULES = ("detect", "refine", "snap", "finalize", "make_final", "route", "scene_multi", "n_signals")


def _cast(old, val):
    """정수 상수에 정수값이면 int 로(RUN 같은 슬라이스 길이), 아니면 값 그대로(DROP=20 dB 에 22.5 가능)."""
    return int(val) if isinstance(old, int) and not isinstance(old, bool) and float(val).is_integer() else val


def _set(key, val):
    parts = key.split(".")
    mod = importlib.import_module(parts[0])
    obj, rest = mod, parts[1:]
    if len(rest) == 1:                                    # 모듈 상수
        old = getattr(mod, rest[0])
        assert not callable(old) and not isinstance(old, dict), f"{key}: 상수가 아님"
        setattr(mod, rest[0], _cast(old, val))
        return lambda: setattr(mod, rest[0], old)
    holder = getattr(mod, rest[0])
    if isinstance(holder, dict):                          # 딕셔너리 항목
        assert rest[1] in holder, f"{key}: 항목 없음"
        old = holder[rest[1]]
        holder[rest[1]] = _cast(old, val)
        return lambda: holder.__setitem__(rest[1], old)
    assert callable(holder), key                          # 함수 기본 인자
    sig = inspect.signature(holder)
    assert rest[1] in sig.parameters and sig.parameters[rest[1]].default is not inspect._empty, f"{key}: 기본 인자 없음"
    names = list(sig.parameters)
    kwd, dfl = dict(holder.__kwdefaults__ or {}), list(holder.__defaults__ or ())
    old = (dict(kwd), list(dfl))
    p = sig.parameters[rest[1]]
    if p.kind == p.KEYWORD_ONLY:
        kwd[rest[1]] = val
        holder.__kwdefaults__ = kwd
    else:
        pos = [n for n in names if sig.parameters[n].kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        i = pos.index(rest[1]) - (len(pos) - len(dfl))
        dfl[i] = val
        holder.__defaults__ = tuple(dfl)

    def undo():
        holder.__kwdefaults__ = old[0] or None
        holder.__defaults__ = tuple(old[1])
    return undo


def apply(cfg):
    """cfg={키: 값}. 반환: 원래대로 되돌리는 함수. 키 하나라도 틀리면 앞서 바꾼 것도 되돌리고 예외."""
    undos = []
    try:
        for k, v in cfg.items():
            undos.append(_set(k, v))
    except Exception:
        for u in reversed(undos):
            u()
        raise
    return lambda: [u() for u in reversed(undos)] and None


def listing():
    out = {}
    for m in MODULES:
        try:
            mod = importlib.import_module(m)
        except Exception as e:                            # make_final 등 외부 의존이 없는 PC 에서만 문제
            out[m] = f"import 실패: {e}"
            continue
        for n, v in vars(mod).items():
            if n.startswith("_"):
                continue
            if isinstance(v, (int, float)) and not isinstance(v, bool) and n.isupper() or n.isupper() and isinstance(v, (int, float)):
                out[f"{m}.{n}"] = v
            elif isinstance(v, dict) and n == "P":
                out.update({f"{m}.P.{k}": x for k, x in v.items() if isinstance(x, (int, float))})
            elif inspect.isfunction(v) and v.__module__ == m:
                for pn, p in inspect.signature(v).parameters.items():
                    if isinstance(p.default, (int, float)) and not isinstance(p.default, bool):
                        out[f"{m}.{n}.{pn}"] = p.default
    return out


def _from_env():
    s = os.environ.get("SONG_TUNE")
    if not s:
        return
    cfg = json.load(open(s[1:], encoding="utf8")) if s.startswith("@") else json.loads(s)
    apply(cfg)


_from_env()

if __name__ == "__main__":
    if sys.argv[1:] == ["list"]:
        for k, v in listing().items():
            print(k, v)
    else:
        # 자가검사: 상수, 딕셔너리 항목, 함수 기본 인자(위치/키워드)를 바꾸고 되돌린다
        import snap, route
        low0, ok0 = snap.LOW, route.P["scene_ok"]                 # 상수를 채택값으로 바꿔도 시험이 깨지지 않게 시작 값을 기억한다
        u = apply({"snap.LOW": 0.4, "route.P.scene_ok": 0.2, "snap.deep_end.depth": 10, "snap.start_s1.vmax": 0.5, "snap.start_s2.maxback": 5.0})
        assert snap.LOW == 0.4 and route.P["scene_ok"] == 0.2
        d = inspect.signature(snap.deep_end).parameters
        assert d["depth"].default == 10 and d["look"].default == 40.0
        assert inspect.signature(snap.start_s1).parameters["vmax"].default == 0.5
        u()
        assert snap.LOW == low0 and route.P["scene_ok"] == ok0 and inspect.signature(snap.deep_end).parameters["depth"].default == 30
        assert inspect.signature(snap.start_s1).parameters["vmax"].default == 0.35
        try:
            apply({"snap.LOW": 1.0, "snap.nonexist": 1})
        except Exception:
            assert snap.LOW == low0                       # 실패하면 앞 항목도 되돌린다
        else:
            raise AssertionError
        print("selftest ok")
