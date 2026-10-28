import sys; sys.path.insert(0, 'experiments')
from bl_sweep import *
import bound_rules as R
sweep({"s3_ext0.25": R.s3(extmu=0.25)})
