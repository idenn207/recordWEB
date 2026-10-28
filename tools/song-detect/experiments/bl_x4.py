"""X15~: SSM novelty 로 시작 당기기, S3 와 조합."""
import sys; sys.path.insert(0, 'experiments')
from bound_lab import *
import bound_rules as R
cfg = {}
for pick in ("max", "last"):
    for b in (20, 45):
        cfg[f"nov_{pick}_b{b}"] = R.nov_start(back=b, pick=pick)
cfg["nov_max_b45_z2"] = R.nov_start(zthr=2.0)
cfg["nov_max_b45_mu0.3"] = R.nov_start(mu=0.3)
batch(cfg, policy=("rev",))
