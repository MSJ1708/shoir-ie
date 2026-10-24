"""Crossed, balanced Gauge R&R ANOVA method for Shoir-IE target T033."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import f as f_distribution


def analyze_crossed_gage_rr(
    measurements: pd.DataFrame,
    *,
    part_col: str,
    appraiser_col: str,
    measurement_col: str,
    tolerance_width: float | None = None,
) -> dict[str, Any]:
    """Analyze a balanced crossed parts×appraisers×replicates Gauge R&R study."""
    if not isinstance(measurements, pd.DataFrame) or measurements.empty:
        raise ValueError("Measurement study requires a non-empty dataframe.")
    if measurements.columns.has_duplicates:
        raise ValueError("Measurement data must have unique column names.")
    if len(measurements) > 100_000:
        raise ValueError("Measurement study is limited to 100000 readings.")
    selected = [part_col, appraiser_col, measurement_col]
    if len(set(selected)) != 3 or any(col not in measurements.columns for col in selected):
        raise ValueError("Select three distinct existing columns for part, appraiser and measurement.")
    frame = measurements[selected].copy(deep=True)
    if frame.isna().any().any():
        raise ValueError("Missing part, appraiser or measurement values are not silently dropped.")
    frame[part_col] = frame[part_col].astype(str).str.strip()
    frame[appraiser_col] = frame[appraiser_col].astype(str).str.strip()
    if (frame[part_col] == "").any() or (frame[appraiser_col] == "").any():
        raise ValueError("Part and appraiser identifiers must be non-empty.")
    try:
        frame[measurement_col] = pd.to_numeric(frame[measurement_col], errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Measurement readings must be numeric.") from exc
    values = frame[measurement_col].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Measurement readings must be finite.")
    parts = sorted(frame[part_col].unique().tolist())
    appraisers = sorted(frame[appraiser_col].unique().tolist())
    if len(parts) < 2:
        raise ValueError("At least two distinct parts are required.")
    if len(appraisers) < 2:
        raise ValueError("At least two distinct appraisers are required.")
    cell_counts = frame.groupby([part_col, appraiser_col], dropna=False).size()
    expected_cells = len(parts) * len(appraisers)
    if len(cell_counts) != expected_cells:
        raise ValueError("The crossed study is incomplete: every part must be measured by every appraiser.")
    if cell_counts.nunique() != 1:
        raise ValueError("The crossed study must be balanced: every part/appraiser cell needs the same number of replicates.")
    replicates = int(cell_counts.iloc[0])
    if replicates < 2:
        raise ValueError("At least two repeated readings per part/appraiser cell are required.")
    tolerance = None
    if tolerance_width is not None and str(tolerance_width).strip() != "":
        try:
            tolerance = float(tolerance_width)
        except (TypeError, ValueError) as exc:
            raise ValueError("Tolerance width must be numeric.") from exc
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("Tolerance width must be finite and positive.")

    p, o, r = len(parts), len(appraisers), replicates
    grand = float(frame[measurement_col].mean())
    part_means = frame.groupby(part_col, sort=True)[measurement_col].mean()
    appraiser_means = frame.groupby(appraiser_col, sort=True)[measurement_col].mean()
    cell_means = frame.groupby([part_col, appraiser_col], sort=True)[measurement_col].mean()
    ss_part = float(o * r * ((part_means - grand) ** 2).sum())
    ss_appraiser = float(p * r * ((appraiser_means - grand) ** 2).sum())
    ss_interaction = 0.0
    for (part, appraiser), mean in cell_means.items():
        ss_interaction += r * float(mean - part_means.loc[part] - appraiser_means.loc[appraiser] + grand) ** 2
    residuals = frame.merge(
        cell_means.rename("_cell_mean"), left_on=[part_col, appraiser_col], right_index=True, validate="many_to_one"
    )
    ss_repeat = float(((residuals[measurement_col] - residuals["_cell_mean"]) ** 2).sum())
    df_part, df_app, df_interaction, df_repeat = p - 1, o - 1, (p - 1) * (o - 1), p * o * (r - 1)
    ms_part = ss_part / df_part
    ms_app = ss_appraiser / df_app
    ms_interaction = ss_interaction / df_interaction
    ms_repeat = ss_repeat / df_repeat

    def f_test(numerator: float, denominator: float, df1: int, df2: int) -> tuple[float | None, float | None]:
        if denominator <= 0:
            return None, None
        statistic = numerator / denominator
        if not math.isfinite(statistic):
            return None, None
        return float(statistic), float(f_distribution.sf(statistic, df1, df2))

    f_part, p_part = f_test(ms_part, ms_interaction, df_part, df_interaction)
    f_app, p_app = f_test(ms_app, ms_interaction, df_app, df_interaction)
    f_inter, p_inter = f_test(ms_interaction, ms_repeat, df_interaction, df_repeat)

    variance_repeat = max(ms_repeat, 0.0)
    variance_interaction_raw = (ms_interaction - ms_repeat) / r
    variance_appraiser_raw = (ms_app - ms_interaction) / (p * r)
    variance_part_raw = (ms_part - ms_interaction) / (o * r)
    variance_components = {
        "Repeatability": variance_repeat,
        "Appraiser": max(variance_appraiser_raw, 0.0),
        "Part × Appraiser": max(variance_interaction_raw, 0.0),
        "Part-to-part": max(variance_part_raw, 0.0),
    }
    grr_variance = variance_components["Repeatability"] + variance_components["Appraiser"] + variance_components["Part × Appraiser"]
    total_variance = grr_variance + variance_components["Part-to-part"]
    total_sd = math.sqrt(total_variance)
    grr_sd = math.sqrt(grr_variance)
    comp_rows = []
    for label, variance in variance_components.items():
        sd = math.sqrt(variance)
        comp_rows.append({
            "component": label,
            "variance_component": float(variance),
            "standard_deviation": float(sd),
            "percent_variance_contribution": float(variance / total_variance * 100) if total_variance > 0 else None,
            "percent_study_variation": float(sd / total_sd * 100) if total_sd > 0 else None,
            "percent_tolerance": float(6 * sd / tolerance * 100) if tolerance is not None else None,
        })
    grr_study_var = grr_sd / total_sd * 100 if total_sd > 0 else None
    ndc = max(1, int(math.floor(1.41 * math.sqrt(variance_components["Part-to-part"] / grr_variance)))) if grr_variance > 0 else None
    anova = pd.DataFrame([
        {"source":"Part","sum_of_squares":ss_part,"df":df_part,"mean_square":ms_part,"F_statistic":f_part,"p_value":p_part},
        {"source":"Appraiser","sum_of_squares":ss_appraiser,"df":df_app,"mean_square":ms_app,"F_statistic":f_app,"p_value":p_app},
        {"source":"Part × Appraiser","sum_of_squares":ss_interaction,"df":df_interaction,"mean_square":ms_interaction,"F_statistic":f_inter,"p_value":p_inter},
        {"source":"Repeatability/Error","sum_of_squares":ss_repeat,"df":df_repeat,"mean_square":ms_repeat,"F_statistic":None,"p_value":None},
    ])
    warnings = [
        "This is a balanced, crossed, random-effects ANOVA approximation; nested, unbalanced or non-crossed designs are not supported.",
        "Negative method-of-moments variance estimates are truncated to zero; inspect the ANOVA table and study design before interpreting components.",
        "The variance-component calculation does not replace a measurement-system specialist's review of resolution, bias, linearity, stability or calibration.",
        "Common screening bands for %GRR or ndc are guidance only; use your organization's standard and measurement-risk context.",
    ]
    return {
        "tool_id": "T033",
        "status": "CALCULATED",
        "method": "Balanced crossed Gauge R&R ANOVA with part×appraiser interaction",
        "assumptions": [
            "Each part is measured by every appraiser with the same replicate count.",
            "Measurements are independent, the measurement process is stable over the study and the random-effects model is appropriate.",
            "Tolerance width, when supplied, uses the same unit as the readings and represents the correct specification width.",
        ],
        "warnings": warnings,
        "metrics": {
            "part_count": int(p),
            "appraiser_count": int(o),
            "replicates_per_cell": int(r),
            "reading_count": int(len(frame)),
            "grand_mean": grand,
            "repeatability_sd": math.sqrt(variance_repeat),
            "reproducibility_sd": math.sqrt(variance_components["Appraiser"] + variance_components["Part × Appraiser"]),
            "total_gage_rr_sd": grr_sd,
            "total_variation_sd": total_sd,
            "percent_grr_study_variation": grr_study_var,
            "number_of_distinct_categories": ndc,
            "tolerance_width": tolerance,
            "negative_variance_components_truncated": bool(variance_interaction_raw < 0 or variance_appraiser_raw < 0 or variance_part_raw < 0),
        },
        "anova_table": anova,
        "variance_components": pd.DataFrame(comp_rows),
        "study_design": {"parts": parts, "appraisers": appraisers, "replicates_per_cell": r},
    }
