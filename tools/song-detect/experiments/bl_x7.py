import sys; sys.path.insert(0, 'experiments')
from bl_sweep import *
import bound_rules as R
sweep({"s3_mu0.2": R.s3(mu=0.2), "e4_50": R.e4(floor=-50.0), "e4_55": R.e4(floor=-55.0), "e5": R.e5(), "breath": R.breath(), "s4": R.s4(), "s3e": R.s3e(), "s3_back20": R.s3(back=20)})
