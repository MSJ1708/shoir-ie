"""Power/sample-size planner for supported mean-comparison t tests (T085)."""
from __future__ import annotations
import math
import pandas as pd
from scipy.stats import nct, t

def plan_t_test_power(*, effect_size_d: float, alpha: float=0.05, target_power: float=0.80,
                      design: str="one_sample", alternative: str="two-sided",
                      specified_sample_size: int|None=None, maximum_sample_size: int=100000) -> dict:
    """Find the minimum N using a noncentral-t power calculation; two-group N is per group."""
    try:
        d,a,pwr=float(effect_size_d),float(alpha),float(target_power)
    except (TypeError,ValueError) as exc:
        raise ValueError("Effect size, alpha and target power must be numeric.") from exc
    if not math.isfinite(d) or d==0: raise ValueError("Effect size d must be finite and non-zero.")
    if not math.isfinite(a) or not 0<a<1: raise ValueError("Alpha must be strictly between 0 and 1.")
    if not math.isfinite(pwr) or not 0<pwr<1: raise ValueError("Target power must be strictly between 0 and 1.")
    design=str(design).strip().lower()
    if design not in {"one_sample","paired","two_independent_equal_n"}:
        raise ValueError("Design must be one of: one_sample, paired, two_independent_equal_n.")
    alternative=str(alternative).strip().lower()
    if alternative not in {"two-sided","greater","less"}:
        raise ValueError("Alternative must be two-sided, greater, or less.")
    if isinstance(maximum_sample_size,bool) or int(maximum_sample_size)!=maximum_sample_size or not 3<=int(maximum_sample_size)<=1_000_000:
        raise ValueError("Maximum sample size must be a whole number from 3 to 1000000.")
    maximum_sample_size=int(maximum_sample_size)
    specified=None
    if specified_sample_size is not None:
        if isinstance(specified_sample_size,bool) or int(specified_sample_size)!=specified_sample_size:
            raise ValueError("Specified sample size must be a whole number.")
        specified=int(specified_sample_size)
        if specified<(2 if design=="two_independent_equal_n" else 3) or specified>maximum_sample_size:
            raise ValueError("Specified sample size is outside the supported integer range.")
    def power(n):
        df,ncp=(2*n-2,d*math.sqrt(n/2)) if design=="two_independent_equal_n" else (n-1,d*math.sqrt(n))
        if alternative=="two-sided":
            c=float(t.ppf(1-a/2,df)); val=nct.sf(c,df,ncp)+nct.cdf(-c,df,ncp)
        elif alternative=="greater": val=nct.sf(float(t.ppf(1-a,df)),df,ncp)
        else: val=nct.cdf(float(t.ppf(a,df)),df,ncp)
        return min(1.0,max(0.0,float(val)))
    n_min=2 if design=="two_independent_equal_n" else 3
    required=next((n for n in range(n_min,maximum_sample_size+1) if power(n)>=pwr),None)
    if required is None:
        raise ValueError(f"Required sample size exceeds configured maximum ({maximum_sample_size}).")
    total=required*2 if design=="two_independent_equal_n" else required
    specified_total=(specified*2 if design=="two_independent_equal_n" else specified) if specified is not None else None
    curve_ns=sorted(set([n_min,required,min(maximum_sample_size,max(n_min,int(required*0.75))),min(maximum_sample_size,required+5)]))
    return {
      "tool_id":"T085","status":"CALCULATED",
      "method":"Noncentral-t power calculation for supported one-sample, paired, and equal-size independent-group t tests",
      "formula":"Power is the noncentral-t tail probability at the selected critical t; ncp=d√n for one-sample/paired and d√(n/2) per group for two equal independent groups.",
      "parameters":{"effect_size_cohens_d":d,"alpha":a,"target_power":pwr,"design":design,"alternative":alternative,
                    "specified_sample_size_per_unit":specified,"maximum_sample_size":maximum_sample_size},
      "assumptions":["Cohen's d is an explicit planning assumption.","The selected t-test model and distributional assumptions apply.",
                     "For two independent groups the sample size is per group; total N is twice that value.",
                     "Attrition, clustering, multiple-comparison adjustments, covariates and complex longitudinal designs are not modeled."],
      "warnings":["A planned sample size does not guarantee significance or valid inference.",
                  "Only one-sample, paired and equal-sized two-independent-group mean t tests are supported."],
      "metrics":{"minimum_sample_size_per_unit":required,"minimum_total_sample_size":total,
                 "achieved_power_at_required_sample_size":power(required),
                 "achieved_power_at_specified_sample_size":power(specified) if specified is not None else None,
                 "specified_total_sample_size":specified_total,
                 "degrees_of_freedom_at_required_sample_size":2*required-2 if design=="two_independent_equal_n" else required-1},
      "power_curve":pd.DataFrame([{"sample_size_per_unit":n,"total_sample_size":n*2 if design=="two_independent_equal_n" else n,
                                   "achieved_power":power(n)} for n in curve_ns])
    }
