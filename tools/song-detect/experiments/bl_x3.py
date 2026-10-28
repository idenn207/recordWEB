import sys; sys.path.insert(0, 'experiments')
from bl_sweep import *
import bound_rules as R
sweep({"s3_default": R.s3(), "s3_mu0.3": R.s3(mu=0.3)})
