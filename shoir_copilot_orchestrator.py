"""Shoir-IE Engineering Copilot workflow orchestrator.

This module turns Copilot into a governed, module-aware engineering workflow:
inspect data -> choose method -> run analysis -> generate graph ->
compare scenarios -> explain -> export.

All analytics are deterministic and grounded in the data already present in
the current Shoir-IE workspace. No external side effects are performed.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Mapping

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


WORKFLOW_STEPS = [
    "Inspect data",
    "Choose method",
    "Run analysis",
    "Generate graph",
    "Compare scenarios",
    "Explain",
    "Export",
]


def _token(value: str) -> str:
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:12]


def _normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def classify_request(prompt: str) -> dict[str, str]:
    p = _normalise_text(prompt)
    if any(k in p for k in ("forecast", "predict demand", "future demand", "time series")):
        return {"intent": "forecast", "label": "Demand forecasting", "reason": "The request refers to future/time-series prediction."}
    if any(k in p for k in ("compare", "scenario", "baseline", "before and after", "delta")):
        return {"intent": "compare", "label": "Scenario comparison", "reason": "The request asks for scenario or baseline comparison."}
    if any(k in p for k in ("correl", "relationship", "association", "drivers")):
        return {"intent": "relationship", "label": "Relationship analysis", "reason": "The request asks which variables move together."}
    if any(k in p for k in ("quality", "defect", "cpk", "control chart", "capability")):
        return {"intent": "quality", "label": "Quality analysis", "reason": "The request references quality or process capability."}
    if any(k in p for k in ("inventory", "safety stock", "reorder", "stockout")):
        return {"intent": "inventory", "label": "Inventory analysis", "reason": "The request references inventory or service-risk measures."}
    if any(k in p for k in ("optimize", "optimization", "milp", "allocation", "schedule", "routing")):
        return {"intent": "optimization", "label": "Optimization readiness", "reason": "The request asks for an optimization, allocation, scheduling or routing workflow."}
    return {"intent": "descriptive", "label": "Engineering data profile", "reason": "No more specific analytical intent was detected, so Copilot starts with a descriptive evidence profile."}


def recommend_module(prompt: str, modules: list[str], current_module: str | None = None) -> tuple[str | None, str]:
    if not modules:
        return current_module, "No module catalog was supplied."
    p = _normalise_text(prompt)
    # Use token overlap rather than hard-coded winner logic. This is a routing
    # mechanism, not an evaluative ranking of engineering modules.
    aliases = {
        "forecast": ("forecast", "demand", "predict", "time series"),
        "inventory": ("inventory", "safety stock", "reorder", "stockout"),
        "quality": ("quality", "defect", "cpk", "control chart", "fmea"),
        "maintenance": ("maintenance", "vibration", "asset health"),
        "simulation": ("simulation", "digital twin", "discrete event", "monte carlo"),
        "optimization": ("optimize", "optimization", "milp", "allocation", "routing", "schedule"),
        "scenario": ("scenario", "compare", "baseline", "before and after"),
        "sustainability": ("carbon", "energy", "sustainability", "emissions"),
        "economics": ("npv", "irr", "payback", "capex", "cost benefit"),
        "research": ("research", "hypothesis", "experiment", "statistical"),
    }
    scored: list[tuple[int, str]] = []
    for module in modules:
        name = _normalise_text(module)
        score = 0
        for group in aliases.values():
            if any(term in p for term in group) and any(term in name for term in group):
                score += 2
        if current_module and _normalise_text(current_module) == name:
            score += 1
        if score:
            scored.append((score, module))
    if scored:
        scored.sort(key=lambda item: (-item[0], item[1]))
        selected = scored[0][1]
        return selected, "Selected from the live module catalog using request-to-module capability overlap."
    return current_module or modules[0], "No specific module intent was detected; using the current workflow context."


def inspect_data(df: pd.DataFrame) -> dict[str, Any]:
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    numeric = [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    date_like = []
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            date_like.append(str(col))
        elif s.dtype == object:
            sample = s.dropna().astype(str).head(30)
            if len(sample) >= 5:
                parsed = pd.to_datetime(sample, errors="coerce")
                if float(parsed.notna().mean()) >= 0.8:
                    date_like.append(str(col))
    return {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "numeric_columns": numeric,
        "date_like_columns": date_like,
        "missing_cells": int(df.isna().sum().sum()) if not df.empty else 0,
        "duplicate_rows": int(df.duplicated().sum()) if not df.empty else 0,
        "column_names": [str(c) for c in df.columns],
    }


def choose_method(intent: str, inspection: Mapping[str, Any]) -> dict[str, Any]:
    numeric = list(inspection.get("numeric_columns", []))
    dates = list(inspection.get("date_like_columns", []))
    if intent == "forecast":
        target = next((c for c in numeric if any(k in c.lower() for k in ("demand", "sales", "qty", "quantity", "volume"))), numeric[0] if numeric else None)
        return {"method": "Demand forecast" if target and dates else "Descriptive profile", "date_column": dates[0] if dates else None, "target_column": target}
    if intent == "relationship":
        return {"method": "Pearson correlation matrix" if len(numeric) >= 2 else "Descriptive profile"}
    if intent == "quality":
        target = next((c for c in numeric if any(k in c.lower() for k in ("defect", "yield", "quality", "value", "measurement", "dimension"))), numeric[0] if numeric else None)
        return {"method": "Quality distribution + summary" if target else "Descriptive profile", "target_column": target}
    if intent == "inventory":
        targets = [c for c in numeric if any(k in c.lower() for k in ("demand", "stock", "inventory", "qty", "quantity", "lead"))]
        return {"method": "Inventory variability profile" if targets else "Descriptive profile", "target_columns": targets}
    if intent == "optimization":
        return {"method": "Optimization readiness assessment", "required_signals": ["objective/cost", "decision variables", "constraints"]}
    if intent == "compare":
        return {"method": "Scenario delta comparison"}
    return {"method": "Descriptive engineering profile"}


def _numeric_frame(df: pd.DataFrame) -> pd.DataFrame:
    numeric = df.select_dtypes(include=np.number)
    return numeric.apply(pd.to_numeric, errors="coerce")


def run_analysis(
    df: pd.DataFrame,
    intent: str,
    method: Mapping[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    data = df.copy(deep=True)
    if data.empty:
        return pd.DataFrame(), {"status": "No data available."}

    if intent == "relationship":
        corr = _numeric_frame(data).corr(numeric_only=True)
        result = corr.reset_index().rename(columns={"index": "Measure"})
        return result, {"status": "Completed", "type": "correlation", "numeric_measures": int(corr.shape[0])}

    if intent == "compare":
        scenario_col = next(
            (c for c in data.columns if "scenario" in str(c).lower() or "case" in str(c).lower()),
            None,
        )
        numeric = [str(c) for c in data.columns if pd.api.types.is_numeric_dtype(data[c])]
        baseline_scenario = next((c for c in data.columns if str(c).lower() in {"baseline", "base"}), None)
        scenario_like = [c for c in data.columns if "baseline" in str(c).lower() or "scenario" in str(c).lower()]
        if scenario_col and len(numeric) >= 1:
            summary = data.groupby(scenario_col, dropna=False)[numeric].mean(numeric_only=True).reset_index()
            return summary, {"status": "Completed", "type": "scenario_grouped", "scenario_column": scenario_col}
        if len(scenario_like) >= 2:
            pairs = []
            for col in scenario_like:
                if pd.api.types.is_numeric_dtype(data[col]):
                    pairs.append(col)
            if len(pairs) >= 2:
                baseline = next((c for c in pairs if "baseline" in str(c).lower()), pairs[0])
                comparison = next((c for c in pairs if c != baseline), pairs[1])
                out = pd.DataFrame({
                    "Metric": [str(c) for c in data.index] if data.index.name else data.columns[:0].tolist()
                })
                deltas = []
                for _, row in data.iterrows():
                    deltas.append({
                        "Baseline": row[baseline],
                        "Comparison": row[comparison],
                        "Delta": row[comparison] - row[baseline],
                        "Delta %": ((row[comparison] - row[baseline]) / row[baseline] * 100) if pd.notna(row[baseline]) and row[baseline] != 0 else np.nan,
                    })
                if deltas:
                    result = pd.DataFrame(deltas)
                    result.insert(0, "Metric", [f"Row {i+1}" for i in range(len(result))])
                    return result, {"status": "Completed", "type": "baseline_comparison", "baseline_column": baseline, "comparison_column": comparison}
        return data, {"status": "Review", "type": "scenario_unavailable", "message": "No explicit scenario structure was found."}

    if intent == "forecast":
        date_col = method.get("date_column")
        target_col = method.get("target_column")
        if date_col and target_col:
            from industrial_platform import ml_demand_forecast
            forecast, metrics = ml_demand_forecast(data, date_col, target_col, [], 12)
            return forecast, {"status": "Completed", "type": "forecast", "metrics": metrics}
        return data, {"status": "Review", "type": "forecast_unavailable", "message": "A date field and numeric demand-like target could not be identified."}

    numeric = _numeric_frame(data)
    summary = (
        numeric.agg(["count", "mean", "median", "std", "min", "max"]).T.reset_index()
        .rename(columns={"index": "Measure"})
        if not numeric.empty else pd.DataFrame({"Measure": ["No numeric measures"]})
    )
    if intent == "quality" and method.get("target_column") and method["target_column"] in data.columns:
        target = pd.to_numeric(data[method["target_column"]], errors="coerce").dropna()
        if not target.empty:
            summary = summary[summary["Measure"] != method["target_column"]]
            summary = pd.concat([
                summary,
                pd.DataFrame([{
                    "Measure": method["target_column"],
                    "count": int(target.count()),
                    "mean": float(target.mean()),
                    "median": float(target.median()),
                    "std": float(target.std(ddof=1)) if len(target) > 1 else 0.0,
                    "min": float(target.min()),
                    "max": float(target.max()),
                }]),
            ], ignore_index=True)

    if intent == "inventory":
        targets = [c for c in method.get("target_columns", []) if c in data.columns]
        if targets:
            rows = []
            for col in targets:
                s = pd.to_numeric(data[col], errors="coerce").dropna()
                if s.empty:
                    continue
                rows.append({
                    "Measure": col,
                    "Mean": float(s.mean()),
                    "Std Dev": float(s.std(ddof=1)) if len(s) > 1 else 0.0,
                    "P95": float(s.quantile(0.95)),
                    "Coefficient of Variation": float(s.std(ddof=1) / s.mean()) if len(s) > 1 and s.mean() != 0 else np.nan,
                })
            return pd.DataFrame(rows), {"status": "Completed", "type": "inventory_profile"}
    if intent == "optimization":
        evidence = {
            "objective/cost signals": [c for c in data.columns if any(k in str(c).lower() for k in ("cost", "price", "objective", "distance", "carbon"))],
            "decision-variable signals": [c for c in data.columns if any(k in str(c).lower() for k in ("qty", "quantity", "flow", "route", "assign", "open"))],
            "constraint signals": [c for c in data.columns if any(k in str(c).lower() for k in ("capacity", "limit", "min", "max", "constraint", "demand"))],
        }
        readiness = "Ready for module-specific optimization" if all(evidence.values()) else "Needs additional optimization inputs"
        result = pd.DataFrame([{"Signal": k, "Detected Fields": ", ".join(v) if v else "None"} for k, v in evidence.items()])
        return result, {"status": "Completed", "type": "optimization_readiness", "readiness": readiness, "signals": evidence}

    return summary.round(6), {"status": "Completed", "type": "descriptive"}


def compare_scenarios(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Explicit scenario comparison helper, independent of request intent."""
    scenario_col = next((c for c in df.columns if "scenario" in str(c).lower() or "case" in str(c).lower()), None)
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if scenario_col and numeric:
        out = df.groupby(scenario_col, dropna=False)[numeric].mean(numeric_only=True).reset_index()
        return out, {"mode": "grouped", "scenario_column": scenario_col}
    baseline = next((c for c in numeric if "baseline" in str(c).lower()), None)
    comparison = next((c for c in numeric if c != baseline and any(k in str(c).lower() for k in ("scenario", "comparison", "actual", "after"))), None) if baseline else None
    if baseline and comparison:
        out = pd.DataFrame({
            "Metric": [f"Row {i+1}" for i in range(len(df))],
            "Baseline": pd.to_numeric(df[baseline], errors="coerce"),
            "Comparison": pd.to_numeric(df[comparison], errors="coerce"),
        })
        out["Delta"] = out["Comparison"] - out["Baseline"]
        out["Delta %"] = np.where(out["Baseline"] != 0, out["Delta"] / out["Baseline"] * 100, np.nan)
        return out, {"mode": "baseline_vs_comparison", "baseline_column": baseline, "comparison_column": comparison}
    return pd.DataFrame(), {"mode": "unavailable"}


def build_graph(df: pd.DataFrame, analysis_type: str = "auto") -> go.Figure | None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    numeric = [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    categorical = [str(c) for c in df.columns if str(c) not in numeric]
    if analysis_type == "correlation":
        matrix = df.copy()
        if "Measure" in matrix.columns:
            matrix = matrix.set_index("Measure")
            numeric_matrix = matrix.apply(pd.to_numeric, errors="coerce")
        else:
            numeric_matrix = _numeric_frame(matrix)
        if numeric_matrix.shape[0] >= 2 and numeric_matrix.shape[1] >= 2:
            return px.imshow(numeric_matrix, text_auto=".2f", aspect="auto", title="Correlation map")

    if "Date" in df.columns and "Forecast" in df.columns:
        fig = px.line(df, x="Date", y="Forecast", markers=True, title="Forecast trajectory")
        if "Lower 95%" in df.columns and "Upper 95%" in df.columns:
            fig.add_scatter(x=df["Date"], y=df["Upper 95%"], mode="lines", name="Upper 95%")
            fig.add_scatter(x=df["Date"], y=df["Lower 95%"], mode="lines", name="Lower 95%")
        return fig
    if categorical and numeric:
        return px.bar(df, x=categorical[0], y=numeric[0], title=f"{numeric[0]} by {categorical[0]}")
    if len(numeric) >= 2:
        return px.scatter(df, x=numeric[0], y=numeric[1], title=f"{numeric[1]} vs {numeric[0]}")
    if numeric:
        return px.histogram(df, x=numeric[0], title=f"Distribution of {numeric[0]}")
    return None


def explain_results(prompt: str, inspection: Mapping[str, Any], method: Mapping[str, Any], meta: Mapping[str, Any], result: pd.DataFrame) -> str:
    parts = [
        f"I inspected {int(inspection.get('rows', 0)):,} rows and {int(inspection.get('columns', 0)):,} columns.",
        f"Copilot selected **{method.get('method', 'analysis')}** based on the request and available fields.",
    ]
    if inspection.get("missing_cells"):
        parts.append(f"The dataset contains {int(inspection['missing_cells']):,} missing cell(s), so those should be considered when interpreting the result.")
    if inspection.get("duplicate_rows"):
        parts.append(f"I found {int(inspection['duplicate_rows']):,} duplicate row(s); they were not silently removed.")
    if meta.get("type") == "forecast":
        metrics = meta.get("metrics", {})
        parts.append(
            "The forecast engine returned an R² of "
            f"{float(metrics.get('R2', 0.0)):.3f} and MAE of {float(metrics.get('MAE', 0.0)):.3f} on the fitted historical data."
        )
    elif meta.get("type") in {"optimization_readiness", "milp_optimization"}:
        if meta.get("type") == "milp_optimization":
            parts.append(
                f"Solver status: {meta.get('solver_status', 'Unknown')}; total cost "
                f"{float(meta.get('total_cost', 0.0)):,.2f} and total carbon "
                f"{float(meta.get('total_carbon', 0.0)):,.2f}."
            )
        else:
            parts.append(str(meta.get("readiness", "Optimization readiness was assessed.")))
    elif meta.get("type") == "scenario_grouped" and not result.empty:
        parts.append(f"The result contains {len(result):,} scenario group(s) summarized across numeric measures.")
    elif meta.get("type") == "baseline_comparison" and not result.empty and "Delta %" in result.columns:
        delta = pd.to_numeric(result["Delta %"], errors="coerce").dropna()
        if not delta.empty:
            parts.append(f"The comparison table contains {len(delta):,} row-level delta calculations; inspect the sign and magnitude rather than treating them as causal effects.")
    elif meta.get("type") == "correlation" and not result.empty:
        parts.append("The correlation matrix is descriptive association evidence; it does not establish causality.")
    elif not result.empty:
        parts.append(f"The analysis produced {len(result):,} output row(s) from the available evidence.")

    return " ".join(parts)


def build_export_bundle(
    prompt: str,
    module: str,
    run_id: str,
    inspection: Mapping[str, Any],
    method: Mapping[str, Any],
    result: pd.DataFrame,
    explanation: str,
    figure: go.Figure | None,
) -> bytes:
    from shoir_upgrade import build_excel_report
    tables = [("Analysis Result", result)]
    if "numeric_columns" in inspection:
        tables.append(("Data Profile", pd.DataFrame([{
            "Rows": inspection.get("rows", 0),
            "Columns": inspection.get("columns", 0),
            "Missing Cells": inspection.get("missing_cells", 0),
            "Duplicate Rows": inspection.get("duplicate_rows", 0),
            "Numeric Fields": len(inspection.get("numeric_columns", [])),
            "Date Fields": len(inspection.get("date_like_columns", [])),
        }])))
    xlsx = build_excel_report("Shoir-IE Engineering Copilot", tables, [(module, figure)] if figure is not None else [])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("request.txt", str(prompt).encode("utf-8"))
        zf.writestr("module.txt", str(module).encode("utf-8"))
        zf.writestr("run_id.txt", str(run_id).encode("utf-8"))
        zf.writestr("inspection.json", json.dumps(dict(inspection), indent=2, default=str).encode("utf-8"))
        zf.writestr("method.json", json.dumps(dict(method), indent=2, default=str).encode("utf-8"))
        zf.writestr("results.csv", result.to_csv(index=False).encode("utf-8"))
        zf.writestr("explanation.md", explanation.encode("utf-8"))
        zf.writestr("copilot_analysis.xlsx", xlsx)
        if figure is not None:
            zf.writestr("chart.html", figure.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8"))
            zf.writestr("chart.json", figure.to_json().encode("utf-8"))
        zf.writestr("manifest.json", json.dumps({
            "contract": WORKFLOW_STEPS,
            "run_id": run_id,
            "module": module,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }, indent=2).encode("utf-8"))
    return buf.getvalue()



def build_workflow_plan(prompt: str, module: str, df: pd.DataFrame, knowledge_documents: int = 0) -> dict[str, Any]:
    """Create the visible, reviewable execution plan before any analysis runs."""
    inspection = inspect_data(df)
    intent = classify_request(prompt)
    method = choose_method(intent["intent"], inspection)
    steps = [
        {"step": "Inspect data", "status": "Ready", "detail": f"{inspection['rows']:,} rows × {inspection['columns']:,} columns; {inspection['missing_cells']:,} missing cells."},
        {"step": "Choose method", "status": "Ready", "detail": method.get("method", "Engineering profile")},
        {"step": "Run analysis", "status": "Ready", "detail": "Read-only, deterministic analysis on the selected dataset."},
        {"step": "Generate graph", "status": "Ready", "detail": "Create a Plotly view from the actual analysis output."},
        {"step": "Compare scenarios", "status": "Conditional", "detail": "Runs when baseline/scenario structure exists in the selected data."},
        {"step": "Explain", "status": "Ready", "detail": f"Translate observed evidence, assumptions and limitations into operator language; {int(knowledge_documents)} linked knowledge document(s) are available as context."},
        {"step": "Export", "status": "Ready", "detail": "Package results, method, data profile and the generated graph."},
    ]
    return {
        "intent": intent,
        "method": method,
        "inspection": inspection,
        "steps": steps,
        "module": module,
        "requires_approval": True,
    }


def run_orchestration(prompt: str, module: str, df: pd.DataFrame, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
    run_id = "COP-" + uuid.uuid4().hex[:12].upper()
    inspection = inspect_data(df)
    intent_info = classify_request(prompt)
    method = choose_method(intent_info["intent"], inspection)
    runtime = dict(context or {})
    knowledge_text = str(runtime.get("knowledge_context") or "").strip()
    knowledge_count = int(runtime.get("knowledge_documents", 0) or 0)
    if intent_info["intent"] == "optimization" and callable(runtime.get("milp_solver")):
        customers = runtime.get("customers") or []
        warehouses = runtime.get("warehouses") or []
        try:
            validation_fn = runtime.get("validate_network_inputs")
            valid, validation_message = validation_fn(customers, warehouses) if callable(validation_fn) else (True, "Validation not supplied.")
            if valid and customers and warehouses:
                customers_tuple = tuple(tuple(sorted(dict(row).items())) for row in customers)
                warehouses_tuple = tuple(tuple(sorted(dict(row).items())) for row in warehouses)
                status, cost_value, carbon_value, allocation = runtime["milp_solver"](customers_tuple, warehouses_tuple, 0.5, 0.3)
                result = pd.DataFrame(allocation)
                analysis_meta = {
                    "status": "Completed" if status == "Optimal" else "Review",
                    "type": "milp_optimization",
                    "solver_status": status,
                    "total_cost": float(cost_value),
                    "total_carbon": float(carbon_value),
                    "validation": validation_message,
                }
            else:
                result, analysis_meta = run_analysis(df, intent_info["intent"], method)
                analysis_meta = {**analysis_meta, "validation": validation_message}
        except Exception as exc:
            result, analysis_meta = run_analysis(df, intent_info["intent"], method)
            analysis_meta = {**analysis_meta, "solver_fallback": f"{type(exc).__name__}: {exc}"}
    else:
        result, analysis_meta = run_analysis(df, intent_info["intent"], method)
    comparison, comparison_meta = compare_scenarios(df)
    if intent_info["intent"] == "compare" and comparison_meta["mode"] != "unavailable":
        result = comparison
        analysis_meta = {**analysis_meta, **comparison_meta, "type": "scenario_grouped" if comparison_meta["mode"] == "grouped" else "baseline_comparison"}
    figure = build_graph(result, analysis_meta.get("type", "auto"))
    explanation = explain_results(prompt, inspection, method, analysis_meta, result)
    export = build_export_bundle(prompt, module, run_id, inspection, method, result, explanation, figure)
    return {
        "run_id": run_id,
        "intent": intent_info,
        "inspection": inspection,
        "method": method,
        "analysis_meta": analysis_meta,
        "comparison": comparison,
        "comparison_meta": comparison_meta,
        "result": result,
        "figure": figure,
        "explanation": explanation,
        "export": export,
        "module": module,
        "prompt": prompt,
        "knowledge_context": knowledge_text[:12000],
        "knowledge_documents": knowledge_count,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
