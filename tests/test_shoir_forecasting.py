import numpy as np
import pandas as pd

from shoir_forecasting import engineering_forecast, infer_forecast_target


def test_engineering_forecast_supports_operational_targets():
    dates = pd.date_range("2024-01-01", periods=30, freq="MS")
    df = pd.DataFrame({
        "Date": dates,
        "Capacity": 100 + np.arange(30) * 1.5,
        "Promotion": (np.arange(30) % 4 == 0).astype(int),
    })
    result, metrics = engineering_forecast(df, "Date", "Capacity", ["Promotion"], horizon=6, holdout=5)
    assert len(result[result["Series"] == "Forecast"]) == 6
    assert "Holdout MAE" in metrics
    assert "Holdout R2" in metrics
    assert {"Forecast","Lower 95%","Upper 95%"} <= set(result.columns)
    assert infer_forecast_target(df.columns, "Capacity") == "Capacity"



def test_infer_datetime_frequency_is_warning_free_and_supports_daily_series():
    import warnings

    from shoir_forecasting import infer_datetime_frequency

    dates = pd.date_range("2026-01-01", periods=6, freq="D")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        frequency = infer_datetime_frequency(dates)

    assert frequency == "D"
    assert captured == []
