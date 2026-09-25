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
