import sys; sys.path.insert(0, 'experiments')
from bound_lab import *
for r in ("E1", "E1b", "E2", "E3", "S1", "S2"):
    run_off({r})
