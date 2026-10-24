"""Dataset version, lineage, and explicit stale-run checks for Shoir-IE target T020."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

import pandas as pd


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def build_dataset_lineage_record(
    data: pd.DataFrame,
    *,
    dataset_name: str,
    source_type: str,
    source_reference: str = "",
    parent_version_id: str = "",
    transformations: Sequence[Mapping[str, Any]] | None = None,
    method_version: str = "shoir-dataset-lineage-v1",
    downstream_runs: pd.DataFrame | Sequence[Mapping[str, Any]] | None = None,
    prior_versions: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a metadata-only dataset version, hash, lineage record and explicit stale-run list.

    Dataset cell contents are fingerprinted but not copied into this metadata record.
    Downstream runs are only compared when the owner supplies the dataset fingerprint
    actually used for that run; missing references are never guessed.
    """
    if not isinstance(data, pd.DataFrame) or data.empty:
        raise ValueError("Dataset lineage requires a non-empty dataframe.")
    if data.columns.has_duplicates:
        raise ValueError("Dataset lineage requires unique column names.")
    if len(data) > 1_000_000 or len(data.columns) > 500:
        raise ValueError("Dataset exceeds the lineage preview limit (1,000,000 rows or 500 columns).")
    name = str(dataset_name or "").strip()
    if not name:
        raise ValueError("Dataset name is required.")
    source_type = str(source_type or "").strip().upper()
    if source_type not in {"IMPORTED", "LIVE", "SYNTHETIC", "USER_ENTERED"}:
        raise ValueError("Source type must be IMPORTED, LIVE, SYNTHETIC or USER_ENTERED.")
    method_version = str(method_version or "").strip()
    if not method_version:
        raise ValueError("Method/version is required.")

    # Preserve row order and data types; hash only, do not persist raw cell data in the lineage object.
    try:
        data_payload = data.to_json(orient="split", date_format="iso", double_precision=15)
    except (TypeError, ValueError) as exc:
        raise ValueError("Dataset cannot be fingerprinted as a supported table.") from exc
    schema = [{"column": str(col), "dtype": str(data[col].dtype)} for col in data.columns]
    dataset_fingerprint = hashlib.sha256(
        _canonical_json({"schema": schema, "data": data_payload}).encode("utf-8")
    ).hexdigest()

    transformation_list = []
    for ix, item in enumerate(transformations or [], start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"Transformation {ix} must be a structured mapping.")
        step = str(item.get("step", "")).strip()
        operation = str(item.get("operation", "")).strip()
        version = str(item.get("method_version", "unspecified")).strip()
        if not step or not operation:
            raise ValueError(f"Transformation {ix} requires step and operation.")
        transformation_list.append({"step": step, "operation": operation, "method_version": version or "unspecified"})

    parent_id = str(parent_version_id or "").strip()
    source_ref = str(source_reference or "").strip()
    version_payload = {
        "dataset_fingerprint": dataset_fingerprint,
        "schema": schema,
        "dataset_name": name,
        "source_type": source_type,
        "source_reference": source_ref,
        "parent_version_id": parent_id,
        "transformations": transformation_list,
        "method_version": method_version,
    }
    version_signature = hashlib.sha256(_canonical_json(version_payload).encode("utf-8")).hexdigest()
    version_id = "DSV-" + version_signature[:16]

    previous = list(prior_versions or [])
    prior_for_same_dataset = [p for p in previous if str(p.get("dataset_name", "")).casefold() == name.casefold()]
    latest_prior = prior_for_same_dataset[-1] if prior_for_same_dataset else None
    changed = bool(latest_prior and latest_prior.get("version_signature") != version_signature)
    old_fingerprint = latest_prior.get("dataset_fingerprint") if latest_prior else None

    if downstream_runs is None:
        run_frame = pd.DataFrame(columns=["run_id", "dataset_fingerprint"])
    else:
        run_frame = downstream_runs.copy(deep=True) if isinstance(downstream_runs, pd.DataFrame) else pd.DataFrame(list(downstream_runs))
    required_run_cols = {"run_id", "dataset_fingerprint"}
    if not run_frame.empty:
        if run_frame.columns.has_duplicates:
            raise ValueError("Downstream run references must have unique column names.")
        missing = sorted(required_run_cols - set(run_frame.columns))
        if missing:
            raise ValueError("Downstream run references are missing columns: " + ", ".join(missing))
    stale_runs, uncheckable_runs = [], []
    for ix, run in enumerate(run_frame.to_dict(orient="records"), start=1):
        run_id = str(run.get("run_id", "") or "").strip()
        fingerprint = str(run.get("dataset_fingerprint", "") or "").strip()
        if not run_id:
            raise ValueError(f"Downstream run row {ix} requires run_id.")
        if not fingerprint:
            uncheckable_runs.append(run_id)
        elif fingerprint != dataset_fingerprint:
            stale_runs.append({"run_id": run_id, "recorded_dataset_fingerprint": fingerprint, "current_dataset_fingerprint": dataset_fingerprint})
    if run_frame.empty:
        downstream_rows = []
    else:
        if run_frame["run_id"].astype(str).duplicated().any():
            raise ValueError("Downstream run IDs must be unique.")
        downstream_rows = run_frame.to_dict(orient="records")

    record = {
        "tool_id": "T020",
        "status": "VERSIONED",
        "method": "Schema-and-content SHA-256 fingerprint with explicit transformation lineage",
        "method_version": method_version,
        "dataset_name": name,
        "source_type": source_type,
        "source_reference": source_ref,
        "parent_version_id": parent_id or None,
        "version_id": version_id,
        "version_signature": version_signature,
        "dataset_fingerprint": dataset_fingerprint,
        "row_count": int(len(data)),
        "column_count": int(len(data.columns)),
        "schema": schema,
        "transformations": transformation_list,
        "changed_since_previous_version": changed,
        "previous_version_id": latest_prior.get("version_id") if latest_prior else None,
        "previous_dataset_fingerprint": old_fingerprint,
        "stale_downstream_runs": stale_runs,
        "uncheckable_downstream_run_ids": uncheckable_runs,
        "downstream_run_references": downstream_rows,
        "raw_dataset_included": False,
        "assumptions": [
            "The fingerprint preserves the current row order, column order, dtype labels and serialized values; semantically equivalent reordered data may have a different fingerprint.",
            "Only entered source and transformation metadata are recorded; external sources are not connected or verified by this method.",
            "A downstream run is flagged stale only when its recorded dataset fingerprint is supplied and differs from the current fingerprint.",
        ],
        "warnings": [
            "The lineage hash supports change detection; it is not a digital signature, access-control mechanism or proof of data authenticity.",
            "The actual dataset cell contents are not stored in this record; the existing workspace may separately store other application state under its established retention and permission rules.",
        ],
        "metrics": {
            "row_count": int(len(data)),
            "column_count": int(len(data.columns)),
            "transformation_count": int(len(transformation_list)),
            "prior_version_count_for_dataset": int(len(prior_for_same_dataset)),
            "changed_since_previous_version": changed,
            "stale_downstream_run_count": int(len(stale_runs)),
            "uncheckable_downstream_run_count": int(len(uncheckable_runs)),
        },
    }
    return record
