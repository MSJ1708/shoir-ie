"""General engineering forecasting engine for Shoir-IE."""
from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


FORECAST_TARGETS = {
    "Demand": ("demand", "sales", "volume", "qty", "quantity", "orders"),
    "Capacity": ("capacity", "throughput", "available"),
    "Downtime": ("downtime", "down time", "failure", "outage"),
    "Inventory": ("inventory", "stock", "on hand", "on_hand"),
    "Lead Time": ("lead time", "lead_time", "cycle time", "delivery"),
    "Quality": ("quality", "defect", "scrap", "yield", "rework"),
    "Energy": ("energy", "power", "kwh", "consumption"),
}


def infer_forecast_target(columns: Sequence[str], subject: str = "Demand") -> str | None:
    aliases = FORECAST_TARGETS.get(subject, FORECAST_TARGETS["Demand"])
    normalized = [(str(c), str(c).lower().replace("_", " ")) for c in columns]
    for original, lowered in normalized:
        if any(alias in lowered for alias in aliases):
            return original
    return None


def engineering_forecast(
    df: pd.DataFrame,
    date_col: str,
    target_col: str,
    external_cols: Sequence[str] = (),
    horizon: int = 12,
    holdout: int | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fit a transparent trend/seasonality regression and produce a forecast."""
    if date_col not in df.columns or target_col not in df.columns:
        raise ValueError("Forecast requires date and target columns.")
    d = df.copy()
    d[date_col] = pd.to_datetime(d[date_col], errors="coerce")
    d[target_col] = pd.to_numeric(d[target_col], errors="coerce")
    d = d.dropna(subset=[date_col, target_col]).sort_values(date_col).reset_index(drop=True)
    if len(d) < 8:
        raise ValueError("At least 8 historical observations are required.")
    if int(horizon) < 1:
        raise ValueError("Forecast horizon must be positive.")

    external = [c for c in external_cols if c in d.columns and c not in {date_col, target_col}]
    def design_frame(frame: pd.DataFrame, trend_offset: int = 0) -> pd.DataFrame:
        out = pd.DataFrame(index=frame.index)
        out["trend"] = np.arange(trend_offset, trend_offset + len(frame))
        # Month is useful for monthly/irregular industrial data without assuming
        # a specific frequency; for shorter/high-frequency data it simply contributes
        # a low-amplitude seasonal feature.
        out["sin_month"] = np.sin(2*np.pi*frame[date_col].dt.month/12)
        out["cos_month"] = np.cos(2*np.pi*frame[date_col].dt.month/12)
        for col in external:
            values = pd.to_numeric(frame[col], errors="coerce")
            fill = float(pd.to_numeric(d[col], errors="coerce").median())
            out[col] = values.fillna(fill)
        return out

    n = len(d)
    test_n = int(holdout) if holdout is not None else min(6, max(2, n // 5))
    test_n = min(max(0, test_n), max(0, n-6))
    train = d.iloc[:-test_n].copy() if test_n else d.copy()
    test = d.iloc[-test_n:].copy() if test_n else pd.DataFrame()
    X_train = design_frame(train)
    model = LinearRegression().fit(X_train, train[target_col])
    fitted = model.predict(X_train)
    residual = train[target_col].to_numpy(dtype=float) - fitted
    residual_sd = float(np.std(residual, ddof=1)) if len(residual) > 1 else 0.0

    holdout_metrics = {}
    if not test.empty:
        X_test = design_frame(test, trend_offset=len(train))
        pred_test = model.predict(X_test)
        holdout_metrics = {
            "Holdout MAE": float(mean_absolute_error(test[target_col], pred_test)),
            "Holdout RMSE": float(math.sqrt(mean_squared_error(test[target_col], pred_test))),
            "Holdout R2": float(r2_score(test[target_col], pred_test)) if len(test) > 1 else float("nan"),
        }

    freq = pd.infer_freq(d[date_col]) or "D"
    future_dates = pd.date_range(d[date_col].iloc[-1], periods=int(horizon)+1, freq=freq)[1:]
    future = pd.DataFrame({date_col: future_dates})
    for col in external:
        future[col] = float(pd.to_numeric(d[col], errors="coerce").dropna().iloc[-1]) if pd.to_numeric(d[col], errors="coerce").notna().any() else 0.0
    X_future = design_frame(future, trend_offset=n)
    pred = model.predict(X_future)
    target_lower_bound = 0.0 if any(token in str(target_col).lower() for token in ("demand","inventory","stock","capacity","downtime","energy","qty","volume","quantity")) else -np.inf
    pred = np.maximum(target_lower_bound, pred) if np.isfinite(target_lower_bound) else pred
    lower = pred - 1.96*residual_sd
    upper = pred + 1.96*residual_sd
    if np.isfinite(target_lower_bound):
        lower = np.maximum(target_lower_bound, lower)

    forecast = pd.DataFrame({
        "Date": future_dates,
        "Forecast": pred,
        "Lower 95%": lower,
        "Upper 95%": upper,
    })
    metrics = {
        "R2 (in-sample)": float(r2_score(train[target_col], fitted)),
        "MAE (in-sample)": float(mean_absolute_error(train[target_col], fitted)),
        "RMSE (in-sample)": float(math.sqrt(mean_squared_error(train[target_col], fitted))),
        "Residual Std": residual_sd,
        "Training Observations": int(len(train)),
        "Holdout Observations": int(len(test)),
        **holdout_metrics,
        "External Drivers": external,
        "Model": "Linear trend + monthly seasonality + optional external drivers",
        "Future Driver Assumption": "Numeric external drivers are held at their last observed value unless a future driver table is supplied.",
    }
    history = d[[date_col, target_col]].rename(columns={date_col:"Date", target_col:"Actual"})
    return pd.concat([history.assign(Series="History"), forecast.assign(Series="Forecast")], ignore_index=True), metrics
