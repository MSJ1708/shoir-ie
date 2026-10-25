"""Deterministic anomaly-screen tests for imported time-series data (T048)."""
import pandas as pd
import pytest

from shoir_100_tool_anomaly_engine import screen_time_series_anomalies


def rows():
    timestamps=pd.date_range("2026-10-19T00:00:00Z",periods=6,freq="D")
    values=[10,11,9,10,11,40]
    return pd.DataFrame({"timestamp":timestamps,"series":["motor-1"]*6,"value":values})


def test_mad_screen_flags_obvious_outlier_and_reports_freshness():
    result=screen_time_series_anomalies(rows(),timestamp_col="timestamp",series_col="series",value_col="value",threshold=3.5,as_of_datetime="2026-10-24T12:00:00Z")
    assert result["status"]=="CALCULATED_OFFLINE_DATA"
    assert result["metrics"]["observation_count"]==6
    table=result["anomaly_table"]
    assert table.loc[table["value"]==40,"anomaly_flag"].iloc[0]
    assert int(table["anomaly_flag"].sum())==1
    assert result["metrics"]["external_connector_live"] is False
    assert result["series_summary"].iloc[0]["latest_data_age_days"]==pytest.approx(0.5)


def test_mad_screen_handles_zero_mad_and_multiple_series_without_infinity():
    frame=pd.DataFrame({
        "timestamp":list(pd.date_range("2026-10-20T00:00:00Z",periods=5,freq="D"))*2,
        "series":["constant"]*5+["variable"]*5,
        "value":[5,5,5,5,8,1,2,1,2,1],
    })
    result=screen_time_series_anomalies(frame,timestamp_col="timestamp",series_col="series",value_col="value",as_of_datetime="2026-10-24T00:00:00Z")
    zero=result["anomaly_table"].query("series_id == 'constant'")
    assert int(zero["anomaly_flag"].sum())==1
    assert zero.loc[zero["value"]==8,"modified_robust_z_score"].isna().all()
    assert result["anomaly_table"]["modified_robust_z_score"].apply(lambda x: x is None or pd.isna(x) or abs(x)<1e6).all()


@pytest.mark.parametrize("frame,match",[
    (pd.DataFrame({"timestamp":["2026-10-20T00:00:00Z"]*5,"series":["A"]*5,"value":[1,2,3,4,5]}),"unique"),
    (pd.DataFrame({"timestamp":pd.date_range("2026-10-20",periods=4),"series":["A"]*4,"value":[1,2,3,4]}),"at least 5"),
])
def test_mad_screen_rejects_duplicate_timestamps_and_short_series(frame,match):
    with pytest.raises(ValueError,match=match):
        screen_time_series_anomalies(frame,timestamp_col="timestamp",series_col="series",value_col="value",as_of_datetime="2026-10-24T00:00:00Z")


def test_mad_screen_requires_timezone_and_valid_threshold():
    with pytest.raises(ValueError,match="include a timezone"):
        screen_time_series_anomalies(rows(),timestamp_col="timestamp",series_col="series",value_col="value",as_of_datetime="2026-10-24T12:00:00")
    with pytest.raises(ValueError,match="between 2 and 10"):
        screen_time_series_anomalies(rows(),timestamp_col="timestamp",series_col="series",value_col="value",threshold=1.2,as_of_datetime="2026-10-24T12:00:00Z")
