"""축 (g) 서비스용 상주 파이썬 작업자: 한 줄 JSON 요청을 표준입력으로 받아 한 줄 JSON 응답을 표준출력으로 낸다. 카드 v2 와 Replayer 를 한 번만 올려 두므로 요청마다 인터프리터 시작/임포트 비용이 없다.
요청 {"id":..,"op":"ping|replay|sweep|plan","args":{..}} -> 응답 {"id":..,"ok":true,"result":{..},"ms":..} / {"id":..,"ok":false,"error":".."}
  replay args: rp, mp, npp (임계 덮어쓰기 dict), registry (기본 true)    sweep args: grid=[{npp:{..}},...]    plan: 매니페스트 stale 단계 수
사용: Go 서비스(harness/svc)가 띄운다. 직접 시험: echo '{"id":1,"op":"ping"}' | python harness/worker.py
shortcut: 요청은 한 번에 하나씩 순차 처리(작업자 프로세스당), 동시성은 작업자 수로."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *
from harness.replay import load_cards, labels, Replayer, metrics

_S = {}


def state():
    if not _S:
        cards = load_cards()
        _S.update(cards=cards, lab=labels(cards), rp=Replayer(cards))
    return _S


def handle(op, a):
    if op == "ping":
        return dict(pid=os.getpid())
    s = state()
    if op == "replay":
        return metrics(s["lab"], s["rp"].run(rp=a.get("rp"), mp=a.get("mp"), npp=a.get("npp"), registry=a.get("registry", True)))
    if op == "sweep":
        return [dict(args=g, m=metrics(s["lab"], s["rp"].run(rp=g.get("rp"), mp=g.get("mp"), npp=g.get("npp"), registry=g.get("registry", False)))) for g in a["grid"]]
    if op == "plan":
        import harness.manifest as M
        r = M.Run()
        return {k: sum(k in v for v in r.plan([x["slug"] for x in rows()]).values()) for k in ("final", "scene", "route")}
    raise ValueError(f"모르는 op {op}")


def main():
    state()
    print(json.dumps(dict(ready=True, pid=os.getpid())), flush=True)
    for line in sys.stdin:
        t = time.perf_counter()
        try:
            q = json.loads(line)
            r = dict(id=q.get("id"), ok=True, result=handle(q["op"], q.get("args") or {}))
        except Exception as e:
            r = dict(id=(q.get("id") if isinstance(q, dict) else None), ok=False, error=f"{type(e).__name__}: {e}")
        r["ms"] = round((time.perf_counter() - t) * 1000, 1)
        print(json.dumps(r, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
