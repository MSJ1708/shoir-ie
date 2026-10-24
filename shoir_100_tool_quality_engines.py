"""Bounded quality-management methods for Shoir-IE targets T038 and T039.

FMEA risk priority numbers are screening aids based on subjective ratings; they
are not objective probabilities or proof of risk acceptance. CAPA/8D records
provide workflow structure only and do not certify root cause or effectiveness.
"""
from __future__ import annotations

from datetime import date
import math
from typing import Any

import pandas as pd


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
        return ""
    return str(value).strip()


def _rows(value: Any, label: str, *, maximum: int = 1000) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        frame = value.copy(deep=True)
    else:
        try:
            frame = pd.DataFrame(list(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be a table or a list of row objects.") from exc
    if frame.empty:
        raise ValueError(f"{label} requires at least one row.")
    if frame.columns.has_duplicates:
        raise ValueError(f"{label} must have unique column names.")
    if len(frame) > maximum:
        raise ValueError(f"{label} is limited to {maximum} rows per run.")
    return frame


def _iso_date(value: Any, label: str, *, required: bool = False) -> str | None:
    raw = _text(value)
    if not raw:
        if required:
            raise ValueError(f"{label} is required in YYYY-MM-DD format.")
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != raw:
        raise ValueError(f"{label} must use YYYY-MM-DD format.")
    return raw


def score_fmea_register(rows: Any) -> dict[str, Any]:
    """Calculate S×O×D RPNs and rank a supplied FMEA register without hiding ratings."""
    frame = _rows(rows, "FMEA register")
    required = {
        "failure_mode", "effect", "cause", "current_controls",
        "severity", "occurrence", "detection",
        "recommended_action", "owner", "due_date", "action_status",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"FMEA register is missing required columns: {', '.join(missing)}.")

    normalized = []
    seen_modes = set()
    for position, raw in enumerate(frame.to_dict(orient="records"), start=1):
        mode = _text(raw.get("failure_mode"))
        effect = _text(raw.get("effect"))
        cause = _text(raw.get("cause"))
        if not mode or not effect or not cause:
            raise ValueError(f"FMEA row {position} requires failure_mode, effect and cause.")
        if mode.casefold() in seen_modes:
            raise ValueError(f"Failure mode '{mode}' is repeated; keep one row per mode or distinguish the modes explicitly.")
        seen_modes.add(mode.casefold())
        scores = {}
        for field in ("severity", "occurrence", "detection"):
            try:
                score_float = float(raw.get(field))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"FMEA row {position}: {field} must be a whole-number rating from 1 to 10.") from exc
            if not math.isfinite(score_float) or not score_float.is_integer() or not 1 <= score_float <= 10:
                raise ValueError(f"FMEA row {position}: {field} must be a whole-number rating from 1 to 10.")
            scores[field] = int(score_float)
        due_date = _iso_date(raw.get("due_date"), f"FMEA row {position} due_date")
        action_status = _text(raw.get("action_status")) or "Open"
        if action_status not in {"Open", "In Progress", "Closed"}:
            raise ValueError(f"FMEA row {position}: action_status must be Open, In Progress, or Closed.")
        recommended_action = _text(raw.get("recommended_action"))
        normalized.append({
            "failure_mode": mode, "effect": effect, "cause": cause,
            "current_controls": _text(raw.get("current_controls")),
            **scores,
            "RPN (S×O×D)": scores["severity"] * scores["occurrence"] * scores["detection"],
            "recommended_action": recommended_action,
            "owner": _text(raw.get("owner")),
            "due_date": due_date or "",
            "action_status": action_status,
        })
    result_frame = pd.DataFrame(normalized)
    result_frame = result_frame.sort_values(
        ["RPN (S×O×D)", "severity", "failure_mode"],
        ascending=[False, False, True],
        kind="stable",
    ).reset_index(drop=True)
    result_frame.insert(0, "Priority rank", range(1, len(result_frame) + 1))
    open_actions = sum(
        bool(row["recommended_action"]) and row["action_status"] != "Closed"
        for row in normalized
    )
    return {
        "tool_id": "T038",
        "status": "CALCULATED",
        "method": "FMEA risk priority number screening: Severity × Occurrence × Detection",
        "formula": "RPN = S × O × D, with each user-rated component on a 1–10 scale",
        "assumptions": [
            "Severity, occurrence and detection scores are human-entered ordinal ratings.",
            "RPNs are used to sort the supplied register; equal products can conceal different risk profiles.",
            "Scoring criteria must be agreed by the organization; no safety or regulatory acceptance threshold is implied.",
        ],
        "warnings": [
            "RPN is a prioritization aid, not an objective probability, certification or proof that a risk is acceptable.",
            "Review high-severity failure modes separately even when their RPN is not the highest.",
        ],
        "metrics": {
            "failure_mode_count": int(len(result_frame)),
            "mean_rpn": float(result_frame["RPN (S×O×D)"].mean()),
            "maximum_rpn": int(result_frame["RPN (S×O×D)"].max()),
            "severity_9_or_10_count": int((result_frame["severity"] >= 9).sum()),
            "actions_not_closed": int(open_actions),
        },
        "register": result_frame,
    }


def build_capa_8d_record(
    *,
    record_id: str,
    problem_statement: str,
    owner: str,
    opened_date: str,
    due_date: str,
    status: str,
    team: str = "",
    containment: str = "",
    root_cause: str = "",
    corrective_actions: str = "",
    verification_evidence: str = "",
    preventive_action: str = "",
    lessons_learned: str = "",
    verified_by: str = "",
    verification_date: str = "",
) -> dict[str, Any]:
    """Validate one CAPA/8D record; closure requires explicit verification evidence."""
    record_id = _text(record_id)
    problem_statement = _text(problem_statement)
    owner = _text(owner)
    if not record_id:
        raise ValueError("CAPA/8D record ID is required.")
    if not problem_statement:
        raise ValueError("Problem statement is required.")
    if not owner:
        raise ValueError("A responsible owner is required.")
    opened = _iso_date(opened_date, "Opened date", required=True)
    due = _iso_date(due_date, "Due date", required=True)
    verified_date = _iso_date(verification_date, "Verification date")
    allowed_status = {"Open", "Containment", "Root Cause Analysis", "Corrective Action", "Verification", "Closed"}
    status = _text(status)
    if status not in allowed_status:
        raise ValueError("CAPA status must be Open, Containment, Root Cause Analysis, Corrective Action, Verification, or Closed.")

    fields = {
        "team": _text(team),
        "containment": _text(containment),
        "root_cause": _text(root_cause),
        "corrective_actions": _text(corrective_actions),
        "verification_evidence": _text(verification_evidence),
        "preventive_action": _text(preventive_action),
        "lessons_learned": _text(lessons_learned),
        "verified_by": _text(verified_by),
        "verification_date": verified_date or "",
    }
    required_for_closure = {
        "team": fields["team"],
        "containment": fields["containment"],
        "root cause": fields["root_cause"],
        "corrective actions": fields["corrective_actions"],
        "verification evidence": fields["verification_evidence"],
        "preventive action": fields["preventive_action"],
        "lessons learned": fields["lessons_learned"],
        "verifier": fields["verified_by"],
        "verification date": fields["verification_date"],
    }
    missing_for_closure = [name for name, value in required_for_closure.items() if not value]
    if status == "Closed" and missing_for_closure:
        raise ValueError("A CAPA/8D record cannot be marked Closed until these are recorded: " + ", ".join(missing_for_closure) + ".")

    completed_sections = sum(bool(value) for value in (
        fields["team"], fields["containment"], fields["root_cause"],
        fields["corrective_actions"], fields["verification_evidence"],
        fields["preventive_action"], fields["lessons_learned"],
    ))
    record = {
        "record_id": record_id,
        "problem_statement": problem_statement,
        "owner": owner,
        "opened_date": opened,
        "due_date": due,
        "status": status,
        **fields,
        "evidence_state": "USER_ENTERED_UNVERIFIED",
    }
    warnings = [
        "This record organizes CAPA/8D work but does not independently establish root cause or corrective-action effectiveness.",
        "Evidence references and reviewer details are user-entered; they are not independently authenticated by this tool.",
    ]
    if status != "Closed":
        warnings.append("The record remains open; closure is not inferred from progress or an entered target date.")
    return {
        "tool_id": "T039",
        "status": "CALCULATED",
        "method": "CAPA/8D structured record with explicit closure prerequisites",
        "assumptions": [
            "Dates use the Gregorian YYYY-MM-DD format.",
            "A Closed status requires all listed sections and verifier/date fields, but entered details still require independent review.",
        ],
        "warnings": warnings,
        "metrics": {
            "sections_completed": int(completed_sections),
            "sections_required": 7,
            "completion_percent": float(completed_sections / 7 * 100),
            "closure_ready": bool(status == "Closed" and not missing_for_closure),
            "evidence_independently_verified": False,
        },
        "record": record,
    }
