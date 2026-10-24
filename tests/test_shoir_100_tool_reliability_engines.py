"""Independent complete/censored sample fixtures for T041 Weibull reliability."""
import numpy as np
import pandas as pd
import pytest
from scipy.stats import weibull_min

from shoir_100_tool_reliability_engines import fit_weibull_reliability


def test_complete_event_weibull_mle_matches_independent_scipy_fit():
    times=np.array([12,18,21,27,32,38,41,48,57,63,71,80],dtype=float)
    data=pd.DataFrame({"time":times,"failed":1})
    expected_shape, _, expected_scale = weibull_min.fit(times, floc=0)
    result=fit_weibull_reliability(data,time_col="time",event_col="failed",horizons=[20,40,80])
    assert result["status"]=="CALCULATED"
    assert result["metrics"]["observed_failures"]==len(times)
    assert result["metrics"]["right_censored_count"]==0
    assert result["parameters"]["shape"]==pytest.approx(expected_shape,rel=2e-3)
    assert result["parameters"]["scale"]==pytest.approx(expected_scale,rel=2e-3)
    assert result["reliability_at_horizons"]["reliability_probability"].between(0,1).all()
    assert result["parameters_confidence_intervals"] is None


def test_right_censored_weibull_fit_reports_censoring_and_monotonic_survival():
    data=pd.DataFrame({
        "time":[10,15,20,25,30,35,40,45,50,55],
        "failed":[1,1,1,1,1,1,0,0,0,0],
    })
    result=fit_weibull_reliability(data,time_col="time",event_col="failed",horizons=[10,20,40,60])
    assert result["metrics"]["observed_failures"]==6
    assert result["metrics"]["right_censored_count"]==4
    survival=result["reliability_at_horizons"]["reliability_probability"].to_numpy()
    assert np.all(np.diff(survival)<=0)
    assert 0 < result["metrics"]["B10_life"] < result["parameters"]["scale"]
    assert result["metrics"]["optimizer_success"] is True


@pytest.mark.parametrize("frame,match",[
    (pd.DataFrame({"time":[0,1,2],"event":[1,1,1]}),"strictly positive"),
    (pd.DataFrame({"time":[1,2,3],"event":[1,2,0]}),"must be 1"),
    (pd.DataFrame({"time":[1,2,3],"event":[1,0,0]}),"At least two observed failures"),
    (pd.DataFrame({"time":[1,1,1],"event":[1,1,1]}),"two distinct observed failure times"),
])
def test_weibull_rejects_invalid_or_unidentifiable_samples(frame,match):
    with pytest.raises(ValueError,match=match):
        fit_weibull_reliability(frame,time_col="time",event_col="event",horizons=[2])


def test_weibull_rejects_invalid_horizons():
    frame=pd.DataFrame({"time":[1,2,3,4],"event":[1,1,1,1]})
    with pytest.raises(ValueError,match="strictly positive"):
        fit_weibull_reliability(frame,time_col="time",event_col="event",horizons=[0])
