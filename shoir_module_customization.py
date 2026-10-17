"""Per-user module customization shared by all Shoir-IE modules.

Profiles are stored in workspace state (the same persistence contract used by
the main application), keyed by user and immutable module identity. Display
aliases never change the internal module identifier or subscription gate.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Mapping, MutableMapping, Sequence

import pandas as pd


PROFILE_STORE_KEY = "shoir_module_profiles_by_user"
PROFILE_WIDGET_PREFIX = "module_profile_widget_"

CHART_CHOICES = (
    "Auto", "Line", "Bar", "Area", "Scatter", "Distribution", "Histogram",
    "Box", "Pie", "Pareto", "Waterfall", "Sankey", "Heatmap",
    "Correlation Heatmap", "Health Heatmap", "Control Chart", "SPC",
    "Anomaly Timeline", "Metric Trend", "Sensitivity Plot", "Gantt",
    "Network Map", "3D Scatter",
)
TARGET_DIRECTIONS = ("At least", "At most", "Near target")
TARGET_STATISTICS = ("Mean", "Median", "Sum", "Minimum", "Maximum", "Latest")


def module_profile_token(module: str) -> str:
    return hashlib.sha1(str(module).encode("utf-8")).hexdigest()[:12]


def default_module_profile(module: str) -> dict[str, Any]:
    return {
        "module_id": str(module),
        "display_name": str(module),
        "project_name": "",
        "site_name": "",
        "owner_team": "",
        "baseline_label": "Baseline",
        "scenario_label": "Scenario",
        "primary_kpi": "",
        "target_enabled": False,
        "target_value": 0.0,
        "target_direction": "At least",
        "target_tolerance": 0.0,
        "target_statistic": "Mean",
        "target_unit": "",
        "preferred_chart": "Auto",
        "decimal_places": 2,
        "tags": [],
        "notes": "",
        "field_labels": {},
        "field_units": {},
        "updated_at": "",
    }


def normalize_module_profile(
    module: str,
    profile: Mapping[str, Any] | None = None,
    valid_columns: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Validate and bound profile data before it is persisted or rendered."""
    source = dict(profile or {})
    result = default_module_profile(module)

    def clean_text(key: str, limit: int, fallback: str = "") -> str:
        value = str(source.get(key, result.get(key, fallback)) or "").strip()
        return value[:limit]

    result["display_name"] = clean_text("display_name", 120) or str(module)[:120]
    result["project_name"] = clean_text("project_name", 160)
    result["site_name"] = clean_text("site_name", 120)
    result["owner_team"] = clean_text("owner_team", 120)
    result["baseline_label"] = clean_text("baseline_label", 80) or "Baseline"
    result["scenario_label"] = clean_text("scenario_label", 80) or "Scenario"
    result["primary_kpi"] = clean_text("primary_kpi", 160)
    result["target_unit"] = clean_text("target_unit", 40)
    result["notes"] = clean_text("notes", 3000)

    result["target_enabled"] = bool(source.get("target_enabled", False))
    for key in ("target_value", "target_tolerance"):
        try:
            number = float(source.get(key, 0.0))
            result[key] = number if math.isfinite(number) else 0.0
        except (TypeError, ValueError, OverflowError):
            result[key] = 0.0
    result["target_tolerance"] = max(0.0, result["target_tolerance"])

    direction = str(source.get("target_direction", "At least"))
    result["target_direction"] = direction if direction in TARGET_DIRECTIONS else "At least"
    statistic = str(source.get("target_statistic", "Mean"))
    result["target_statistic"] = statistic if statistic in TARGET_STATISTICS else "Mean"
    chart = str(source.get("preferred_chart", "Auto"))
    result["preferred_chart"] = chart if chart in CHART_CHOICES else "Auto"
    try:
        result["decimal_places"] = max(0, min(6, int(source.get("decimal_places", 2))))
    except (TypeError, ValueError, OverflowError):
        result["decimal_places"] = 2

    tags = source.get("tags", [])
    if isinstance(tags, str):
        tags = re.split(r"[,;\n]", tags)
    if not isinstance(tags, (list, tuple, set)):
        tags = []
    clean_tags = []
    for tag in tags:
        label = str(tag or "").strip()[:40]
        if label and label.casefold() not in {x.casefold() for x in clean_tags}:
            clean_tags.append(label)
        if len(clean_tags) >= 12:
            break
    result["tags"] = clean_tags

    columns = None if valid_columns is None else {str(c) for c in valid_columns}
    for source_key, target_key in (("field_labels", "field_labels"), ("field_units", "field_units")):
        raw_mapping = source.get(source_key, {})
        mapping = {}
        if isinstance(raw_mapping, Mapping):
            for original, display in raw_mapping.items():
                original = str(original)
                value = str(display or "").strip()
                if columns is not None and original not in columns:
                    continue
                if not value:
                    continue
                mapping[original] = value[:120 if target_key == "field_labels" else 40]
        result[target_key] = mapping

    if columns is not None and result["primary_kpi"] not in columns:
        result["primary_kpi"] = ""
    result["updated_at"] = str(source.get("updated_at", "") or "")[:64]
    return result


def get_module_profile(
    session_state: MutableMapping[str, Any],
    module: str,
    username: str = "unknown",
    valid_columns: Sequence[Any] | None = None,
) -> dict[str, Any]:
    store = session_state.get(PROFILE_STORE_KEY, {})
    if not isinstance(store, dict):
        store = {}
        session_state[PROFILE_STORE_KEY] = store
    user_key = str(username or "unknown").strip().casefold() or "unknown"
    user_profiles = store.get(user_key, {})
    if not isinstance(user_profiles, dict):
        user_profiles = {}
    profile = user_profiles.get(module_profile_token(module), {})
    return normalize_module_profile(module, profile, valid_columns=valid_columns)


def save_module_profile(
    session_state: MutableMapping[str, Any],
    module: str,
    username: str,
    profile: Mapping[str, Any],
    valid_columns: Sequence[Any] | None = None,
) -> dict[str, Any]:
    store = session_state.get(PROFILE_STORE_KEY, {})
    if not isinstance(store, dict):
        store = {}
    user_key = str(username or "unknown").strip().casefold() or "unknown"
    user_profiles = store.get(user_key, {})
    if not isinstance(user_profiles, dict):
        user_profiles = {}
    from datetime import datetime, timezone

    candidate = dict(profile)
    candidate["updated_at"] = datetime.now(timezone.utc).isoformat()
    cleaned = normalize_module_profile(module, candidate, valid_columns=valid_columns)
    user_profiles[module_profile_token(module)] = cleaned
    store[user_key] = user_profiles
    session_state[PROFILE_STORE_KEY] = store
    return cleaned


def display_field_label(column: Any, profile: Mapping[str, Any] | None = None) -> str:
    source = str(column)
    profile = profile or {}
    labels = profile.get("field_labels", {})
    units = profile.get("field_units", {})
    label = str(labels.get(source) or source) if isinstance(labels, Mapping) else source
    unit = str(units.get(source) or "").strip() if isinstance(units, Mapping) else ""
    return f"{label} ({unit})" if unit else label


def apply_display_labels(
    frame: pd.DataFrame,
    profile: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Return a presentation-only copy; source column names remain unchanged."""
    result = frame.copy(deep=True)
    proposed = [display_field_label(column, profile) for column in result.columns]
    seen: dict[str, int] = {}
    unique = []
    for label in proposed:
        seen[label] = seen.get(label, 0) + 1
        unique.append(label if seen[label] == 1 else f"{label} ({seen[label]})")
    result.columns = unique
    return result


def evaluate_kpi_target(values: Any, profile: Mapping[str, Any]) -> dict[str, Any] | None:
    """Evaluate a user-configured KPI target without treating it as verified savings."""
    if not bool(profile.get("target_enabled")):
        return None
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    if series.empty:
        return None
    statistic = str(profile.get("target_statistic", "Mean"))
    calculations = {
        "Mean": lambda s: float(s.mean()),
        "Median": lambda s: float(s.median()),
        "Sum": lambda s: float(s.sum()),
        "Minimum": lambda s: float(s.min()),
        "Maximum": lambda s: float(s.max()),
        "Latest": lambda s: float(s.iloc[-1]),
    }
    actual = calculations.get(statistic, calculations["Mean"])(series)
    target = float(profile.get("target_value", 0.0))
    tolerance = max(0.0, float(profile.get("target_tolerance", 0.0)))
    direction = str(profile.get("target_direction", "At least"))
    if direction == "At most":
        passed = actual <= target + tolerance
    elif direction == "Near target":
        passed = abs(actual - target) <= tolerance
    else:
        passed = actual >= target - tolerance
    return {
        "actual": actual,
        "target": target,
        "difference": actual - target,
        "tolerance": tolerance,
        "passed": bool(passed),
        "direction": direction,
        "statistic": statistic,
        "observations": int(len(series)),
        "unit": str(profile.get("target_unit", "") or ""),
    }


def _mapping_frame(frame: pd.DataFrame, profile: Mapping[str, Any]) -> pd.DataFrame:
    labels = profile.get("field_labels", {})
    units = profile.get("field_units", {})
    return pd.DataFrame({
        "Source field": [str(column) for column in frame.columns],
        "Display label": [str(labels.get(str(column), "") or "") for column in frame.columns],
        "Unit": [str(units.get(str(column), "") or "") for column in frame.columns],
    })


def render_module_customization(
    module: str,
    username: str,
    frame: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Render an opt-in profile editor used by the common module workspace."""
    import streamlit as st

    frame = frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    profile = get_module_profile(st.session_state, module, username, valid_columns=list(frame.columns))
    notice = st.session_state.pop("shoir_module_profile_saved_notice", None)
    if isinstance(notice, dict) and notice.get("username") == str(username).casefold() and notice.get("module") == module:
        st.success(f"Personalization saved for {profile['display_name']}.")

    token = module_profile_token(module)
    widget = PROFILE_WIDGET_PREFIX + token
    with st.expander("🛠️ Personalize this module", expanded=False):
        st.caption(
            "Customize the working name, project context, KPI target, chart defaults and presentation labels. "
            "These settings are private to your account and this module; the internal module identity and tier access do not change."
        )
        columns = list(frame.columns)
        source_names = [str(column) for column in columns]
        can_map = bool(columns) and len(source_names) == len(set(source_names))
        if columns and not can_map:
            st.warning("Presentation labels are paused because this table has duplicate column names. Make column names unique before mapping them.")

        with st.form(widget + "_form", clear_on_submit=False):
            c1, c2 = st.columns(2)
            with c1:
                display_name = st.text_input("Your module/workspace name", value=profile["display_name"], key=widget + "_display_name", max_chars=120)
                project_name = st.text_input("Project / study name", value=profile["project_name"], key=widget + "_project", max_chars=160)
                site_name = st.text_input("Plant / site / department", value=profile["site_name"], key=widget + "_site", max_chars=120)
                owner_team = st.text_input("Owner / team", value=profile["owner_team"], key=widget + "_owner", max_chars=120)
                tags_text = st.text_input("Tags (comma-separated)", value=", ".join(profile["tags"]), key=widget + "_tags")
            with c2:
                baseline_label = st.text_input("Baseline label", value=profile["baseline_label"], key=widget + "_baseline", max_chars=80)
                scenario_label = st.text_input("Alternative / scenario label", value=profile["scenario_label"], key=widget + "_scenario", max_chars=80)
                numeric_columns = [str(c) for c in columns if pd.api.types.is_numeric_dtype(frame[c])]
                kpi_options = ["(Not configured)"] + numeric_columns
                current_kpi = profile["primary_kpi"] if profile["primary_kpi"] in numeric_columns else "(Not configured)"
                primary_kpi = st.selectbox("Primary KPI to monitor", kpi_options, index=kpi_options.index(current_kpi), key=widget + "_kpi")
                target_enabled = st.checkbox("Enable a local KPI target check", value=profile["target_enabled"], key=widget + "_target_enabled")
                target_value = st.number_input("Target value", value=float(profile["target_value"]), min_value=-1e12, max_value=1e12, key=widget + "_target_value", disabled=not target_enabled)
                target_direction = st.selectbox("Target rule", TARGET_DIRECTIONS, index=TARGET_DIRECTIONS.index(profile["target_direction"]), key=widget + "_target_direction", disabled=not target_enabled)
                target_tolerance = st.number_input("Target tolerance", min_value=0.0, max_value=1e12, value=float(profile["target_tolerance"]), key=widget + "_target_tolerance", disabled=not target_enabled)
                target_statistic = st.selectbox("KPI summary statistic", TARGET_STATISTICS, index=TARGET_STATISTICS.index(profile["target_statistic"]), key=widget + "_target_statistic", disabled=not target_enabled)
                target_unit = st.text_input("KPI unit", value=profile["target_unit"], key=widget + "_target_unit", max_chars=40, disabled=not target_enabled)
                preferred_chart = st.selectbox("Default visualization", CHART_CHOICES, index=CHART_CHOICES.index(profile["preferred_chart"]), key=widget + "_chart")

            mapping = _mapping_frame(frame, profile) if can_map else pd.DataFrame()
            if can_map:
                st.markdown("**Display labels and units**")
                st.caption("These are presentation-only aliases. The original column names stay intact for calculations, import mappings and integrations.")
                mapping_edited = st.data_editor(
                    mapping,
                    use_container_width=True,
                    hide_index=True,
                    disabled=["Source field"],
                    key=widget + "_field_map",
                )
            else:
                mapping_edited = pd.DataFrame()

            notes = st.text_area("Team instructions / assumptions", value=profile["notes"], height=90, key=widget + "_notes", max_chars=3000)
            decimal_places = st.slider("Numeric display precision", min_value=0, max_value=6, value=int(profile["decimal_places"]), key=widget + "_precision")
            submitted = st.form_submit_button("💾 Save module profile", type="primary", use_container_width=True)

        if submitted:
            field_labels = {}
            field_units = {}
            if can_map and isinstance(mapping_edited, pd.DataFrame):
                for record in mapping_edited.to_dict("records"):
                    source = str(record.get("Source field", ""))
                    if source not in source_names:
                        continue
                    label = str(record.get("Display label", "") or "").strip()
                    unit = str(record.get("Unit", "") or "").strip()
                    if label and label != source:
                        field_labels[source] = label
                    if unit:
                        field_units[source] = unit
            candidate = {
                **profile,
                "display_name": display_name,
                "project_name": project_name,
                "site_name": site_name,
                "owner_team": owner_team,
                "baseline_label": baseline_label,
                "scenario_label": scenario_label,
                "primary_kpi": "" if primary_kpi == "(Not configured)" else primary_kpi,
                "target_enabled": target_enabled,
                "target_value": target_value,
                "target_direction": target_direction,
                "target_tolerance": target_tolerance,
                "target_statistic": target_statistic,
                "target_unit": target_unit,
                "preferred_chart": preferred_chart,
                "decimal_places": decimal_places,
                "tags": tags_text,
                "notes": notes,
                "field_labels": field_labels,
                "field_units": field_units,
            }
            profile = save_module_profile(
                st.session_state, module, username, candidate, valid_columns=source_names
            )
            # Persist immediately before rerendering; don't rely only on the
            # bottom-of-page autosave path for this explicit Save action.
            persisted = False
            try:
                from workspace_persistence import save_user_workspace
                persisted = bool(save_user_workspace(username, st.session_state))
            except Exception:
                persisted = False
            st.session_state["shoir_module_profile_saved_notice"] = {
                "username": str(username).casefold(), "module": module
            }
            if persisted:
                st.rerun()
            st.warning("Profile updated in this session, but durable workspace persistence could not be confirmed.")

    return get_module_profile(st.session_state, module, username, valid_columns=list(frame.columns))
