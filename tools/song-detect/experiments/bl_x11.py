"""S1b: 짧은 디지털 무음 뒤 재시작(사운드체크 #111)."""
import sys; sys.path.insert(0, 'experiments')
from bound_lab import *
import bound_rules as R
cfg = {"s1b_default": R.s1b(), "s1b_w8": R.s1b(within=8.0), "s1b_w20": R.s1b(within=20.0), "s1b_sil0.3": R.s1b(silmin=0.3), "s1b_deep-50": R.s1b(deep=-50.0), "s1b_deep-60": R.s1b(deep=-60.0), "s1b_v0.5": R.s1b(vmax=0.5)}
batch(cfg, policy=("all",))
