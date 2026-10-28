"""X21~: 단독 최선 규칙의 조합/순서/정책 비교(새 golden 분류 포함)."""
import sys; sys.path.insert(0, 'experiments')
from bound_lab import *
import bound_rules as R
S3 = R.s3(); S3m2 = R.s3(mu=0.2); S3m3 = R.s3(mu=0.3); E4 = R.e4(floor=-50.0); E4b = R.e4(floor=-55.0)
cfg = {"c_s3": S3, "c_s3_mu0.2": S3m2, "c_s3_mu0.3": S3m3, "c_e4_50": E4, "c_e4_55": E4b,
       "c_s3+e4": R.seq(S3, E4), "c_s3mu0.2+e4": R.seq(S3m2, E4), "c_e4+s3": R.seq(E4, S3),
       "c_s3+breath": R.seq(S3, R.breath()), "c_breath+s3": R.seq(R.breath(), S3), "c_s3+s4+e4": R.seq(S3, R.s4(), E4),
       "c_s3+e4+e5": R.seq(S3, E4, R.e5())}
batch(cfg, policy=("all", "rev"))
# 규칙 순서: S3 를 lead_start 뒤(S1/S2 앞) 또는 S1/S2 뒤, E4 를 E1b 앞/뒤
for n, h in {"o_s3_after_lead": {"after_lead": S3}, "o_s3_after_S12": {"after_S12": S3},
             "o_e4_after_E1": {"after_E1": E4}, "o_e4_after_E1b": {"after_E1b": E4}, "o_e4_after_E3": {"after_E3": E4}, "o_e4_after_S12": {"after_S12": E4},
             "o_both_early": {"after_lead": S3, "after_E1": E4}}.items():
    run_hooks(n, h)
