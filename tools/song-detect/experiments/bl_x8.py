"""X: S3 에 기존 EXT_MU(Singing+Music 평균 >= 0.25) 가드 재사용 + 이동 하한/말 가드 변형."""
import sys; sys.path.insert(0, 'experiments')
from bound_lab import *
import bound_rules as R
cfg = {"x_s3_ext0.2": R.s3(extmu=0.2), "x_s3_ext0.25": R.s3(extmu=0.25), "x_s3_ext0.3": R.s3(extmu=0.3),
       "x_s3_ext0.25_back20": R.s3(extmu=0.25, back=20), "x_s3_ext0.25_back45": R.s3(extmu=0.25, back=45), "x_s3_ext0.25_spf0.3": R.s3(extmu=0.25, spf=0.3),
       "x_s3_ext0.25_thr-55": R.s3(extmu=0.25, thr=-55.0), "x_s3_ext0.25_move3": R.s3(extmu=0.25, minmove=3.0), "x_s3_ext0.25_min1": R.s3(extmu=0.25, minlen=1.0)}
batch(cfg, policy=("all", "rev"))
