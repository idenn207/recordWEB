"""X01~X05: S3 (시작 앞 마지막 깊은 무음 끝) 단독 + 격자."""
import sys; sys.path.insert(0, 'experiments')
from bound_lab import *
import bound_rules as R
cfg = {}
cfg["s3_default"] = R.s3()
for b in (10, 15, 20, 45, 60): cfg[f"s3_back{b}"] = R.s3(back=b)
for t in (-45, -55, -60, -65): cfg[f"s3_thr{t}"] = R.s3(thr=t)
for r in (30, 35, 40): cfg[f"s3_rel{r}"] = R.s3(rel=r)
for f in (0.2, 0.3, 0.6, 2.0): cfg[f"s3_spf{f}"] = R.s3(spf=f)
for m in (0.2, 0.3, 0.5): cfg[f"s3_mu{m}"] = R.s3(mu=m)
for l in (0.3, 1.0, 2.0): cfg[f"s3_min{l}"] = R.s3(minlen=l)
cfg["s3_noskip"] = R.s3(skip_moved=False)
cfg["s3_spfloor"] = R.s3(spfloor=True)
batch(cfg, policy=("all", "rev"))
