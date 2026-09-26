"""Deterministic performance benchmark harness for engineering utilities."""
from __future__ import annotations
import time
import pandas as pd
from industrial_platform import data_quality_report

def benchmark_quality(rows: int = 10000) -> dict:
    rows=int(rows)
    if rows < 1: raise ValueError("rows must be positive")
    df=pd.DataFrame({"id":range(rows),"value":[1.0]*rows})
    start=time.perf_counter()
    result=data_quality_report(df)
    elapsed_ms=(time.perf_counter()-start)*1000
    return {"rows":rows,"duration_ms":round(elapsed_ms,3),"quality_score":result["score"]}

if __name__=="__main__":
    for rows in (10_000,100_000):
        print(benchmark_quality(rows))


def benchmark_callable(label: str, callback, repetitions: int = 3, warmup: int = 1) -> dict:
    """Measure a supplied workflow without assuming a preferred result."""
    repetitions = max(1, int(repetitions))
    warmup = max(0, int(warmup))
    for _ in range(warmup):
        callback()
    samples = []
    for _ in range(repetitions):
        started = time.perf_counter()
        callback()
        samples.append((time.perf_counter() - started) * 1000.0)
    series = pd.Series(samples, dtype=float)
    return {
        "label": str(label),
        "repetitions": repetitions,
        "mean_ms": round(float(series.mean()), 3),
        "median_ms": round(float(series.median()), 3),
        "p95_ms": round(float(series.quantile(0.95)), 3),
        "min_ms": round(float(series.min()), 3),
        "max_ms": round(float(series.max()), 3),
        "samples_ms": [round(float(x), 3) for x in samples],
    }


def calculate_roi_evidence(
    baseline_minutes: float,
    shoir_minutes: float,
    annual_runs: float,
    hourly_rate: float,
    implementation_cost: float = 0.0,
    adoption_fraction: float = 1.0,
) -> dict:
    """Calculate transparent ROI evidence from measured inputs and explicit assumptions."""
    baseline = max(0.0, float(baseline_minutes))
    shoir = max(0.0, float(shoir_minutes))
    runs = max(0.0, float(annual_runs))
    rate = max(0.0, float(hourly_rate))
    cost = max(0.0, float(implementation_cost))
    adoption = min(1.0, max(0.0, float(adoption_fraction)))
    hours_saved_per_run = max(0.0, baseline - shoir) / 60.0
    annual_hours_saved = hours_saved_per_run * runs * adoption
    annual_labor_value = annual_hours_saved * rate
    first_year_net = annual_labor_value - cost
    payback_months = (cost / annual_labor_value * 12.0) if annual_labor_value > 0 else None
    cycle_reduction_pct = ((baseline - shoir) / baseline * 100.0) if baseline > 0 else None
    return {
        "baseline_minutes_per_run": baseline,
        "shoir_minutes_per_run": shoir,
        "annual_runs": runs,
        "hourly_rate": rate,
        "implementation_cost": cost,
        "adoption_fraction": adoption,
        "hours_saved_per_run": hours_saved_per_run,
        "annual_hours_saved": annual_hours_saved,
        "annual_labor_value": annual_labor_value,
        "first_year_net_value": first_year_net,
        "payback_months": payback_months,
        "cycle_reduction_pct": cycle_reduction_pct,
        "evidence_status": "User-entered measurement + explicit assumptions",
    }
