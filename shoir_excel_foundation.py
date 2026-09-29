"""Excel Studio foundation: dataset-first governance, fidelity, contracts, scale and durable versions.

This module is deliberately additive. It consumes the existing Excel Studio result
contract and upgrades it into first-class industrial datasets without replacing the
existing cleaning/rendering engines.
"""
from __future__ import annotations
import logging

import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from typing import Any, Mapping

import numpy as np
import pandas as pd


FOUNDATION_VERSION = "2.0"

# Industrial vocabulary is intentionally broad but conservative. The goal is to
# classify evidence and propose mappings, never silently reinterpret business data.
INDUSTRIAL_SYNONYMS: dict[str, set[str]] = {
    "Asset": {"asset", "assetid", "equipment", "equipmentid", "machine", "machineid", "workcenter", "workcentre"},
    "Process": {"process", "processid", "operation", "operationid", "routing", "workcenterprocess"},
    "Product": {"product", "productid", "sku", "item", "itemid", "finishedgood", "part", "partnumber"},
    "Material": {"material", "materialid", "component", "componentid", "rawmaterial"},
    "Order": {"order", "orderid", "workorder", "workorderid", "productionorder", "purchaseorder", "po"},
    "Workforce": {"employee", "employeeid", "operator", "operatorid", "worker", "person", "userid"},
    "Quality": {"quality", "defect", "defects", "scrap", "scraprate", "yield", "fpy", "rework", "reject"},
    "Maintenance": {"failure", "failureid", "downtime", "mtbf", "mttr", "maintenance", "workordermaintenance"},
    "Energy": {"energy", "power", "electricity", "kwh", "mwh", "consumption"},
    "Cost": {"cost", "unitcost", "totalcost", "price", "expense", "laborcost", "materialcost"},
    "Time": {"date", "datetime", "timestamp", "time", "start", "end", "duration", "cycle", "leadtime"},
    "Inventory": {"inventory", "stock", "onhand", "safety", "reorder", "warehouse"},
    "Transport": {"transport", "shipment", "route", "truck", "vehicle", "carrier", "delivery"},
    "Carbon": {"carbon", "co2", "emissions", "emission"},
}

MEASURE_HINTS = {
    "qty", "quantity", "volume", "demand", "output", "throughput", "rate", "ratio",
    "cost", "price", "duration", "time", "temperature", "pressure", "speed",
    "power", "energy", "defect", "scrap", "yield", "availability", "performance",
    "quality", "distance", "inventory", "stock", "capacity", "utilization",
}

TIME_HINTS = {"date", "datetime", "timestamp", "time", "start", "end", "month", "week", "year", "shift"}
KEY_HINTS = {"id", "code", "sku", "serial", "number", "order", "asset", "employee", "material", "product"}

CONTRACT_BLOCKING_ISSUES = {
    "Required identifier non-null",
    "Numeric fields contain valid numeric values",
    "Percentage fields remain within 0..1 after normalization",
    "Potential secret/security exposure",
}


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def frame_hash(df: pd.DataFrame, sample_limit: int = 250_000) -> str:
    """Stable content fingerprint without retaining source values in metadata."""
    sample = df if len(df) <= sample_limit else pd.concat([df.head(sample_limit // 2), df.tail(sample_limit // 2)])
    payload = sample.to_json(orient="split", date_format="iso", default_handler=str)
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def schema_hash(df: pd.DataFrame) -> str:
    payload = json.dumps(
        [{"field": str(c), "dtype": str(df[c].dtype)} for c in df.columns],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24].upper()


def _candidate_entity(field: str) -> tuple[str, float]:
    n = _norm(field)
    if not n:
        return "Unknown", 0.0
    scored: list[tuple[float, str]] = []
    for entity, terms in INDUSTRIAL_SYNONYMS.items():
        best = 0.0
        for term in terms:
            t = _norm(term)
            if not t:
                continue
            if n == t:
                best = max(best, 1.0)
            elif t in n or n in t:
                best = max(best, 0.82)
        if best:
            scored.append((best, entity))
    if not scored:
        return "Unknown", 0.0
    scored.sort(reverse=True)
    return scored[0][1], scored[0][0]


def classify_field(field: str, series: pd.Series) -> dict[str, Any]:
    """Return conservative industrial semantics for one field."""
    entity, entity_score = _candidate_entity(field)
    n = _norm(field)
    is_numeric = pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)
    is_time = pd.api.types.is_datetime64_any_dtype(series) or bool(set(re.findall(r"[a-z]+", str(field).casefold())) & TIME_HINTS)
    is_key = bool(set(re.findall(r"[a-z]+", str(field).casefold())) & KEY_HINTS) or n.endswith("id")
    is_measure = is_numeric or bool(set(re.findall(r"[a-z]+", str(field).casefold())) & MEASURE_HINTS)
    role = "Key" if is_key else "Time" if is_time else "Measure" if is_measure else "Dimension"
    unit = ""
    match = re.search(r"[\(\[]\s*([^\)\]]+)\s*[\)\]]", str(field))
    if match:
        unit = match.group(1).strip()
    confidence = max(entity_score, 0.9 if is_key and n.endswith("id") else 0.72 if is_measure else 0.60)
    canonical_field = n.replace(" ", "_") or "field"
    canonical_field = re.sub(r"^(asset|product|material|order|employee|operator|machine)_?(id|number|no)?$", lambda m: f"{_norm(m.group(1))}_id", canonical_field)
    return {
        "Entity": entity,
        "Role": role,
        "Canonical field": canonical_field,
        "Unit": unit,
        "Confidence": round(min(0.99, confidence), 2),
        "Evidence": "name/semantic signal" if entity_score else "datatype/field-role signal",
    }


def build_dataset_registry(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Promote every discovered table into a first-class dataset."""
    frames = result.get("table_datasets") or {}
    catalog = {str(x.get("Dataset ID")): x for x in result.get("table_catalog", [])}
    if not frames:
        frames = {str(sheet): frame for sheet, frame in (result.get("cleaned_sheets") or {}).items()}

    source_hash = str(result.get("signature", ""))
    filename = str(result.get("filename", ""))
    datasets: list[dict[str, Any]] = []
    for ordinal, (key, frame) in enumerate(frames.items(), 1):
        frame = frame if isinstance(frame, pd.DataFrame) else pd.DataFrame(frame)
        table_meta = catalog.get(str(key), {})
        table_id = str(table_meta.get("Table ID") or key.split("::")[-1] or f"T{ordinal:03d}")
        raw_identity = f"{source_hash}|{key}|{schema_hash(frame)}"
        dataset_id = "DS-" + hashlib.sha256(raw_identity.encode("utf-8")).hexdigest()[:16].upper()
        fields = [classify_field(str(c), frame[c]) for c in frame.columns]
        grain = [
            str(c) for c, sem in zip(frame.columns, fields)
            if sem["Role"] == "Key"
        ]
        datasets.append({
            "Dataset ID": dataset_id,
            "Dataset key": str(key),
            "Version": 1,
            "Name": f"{filename} · {key}",
            "Source hash": source_hash,
            "Source sheet": str(table_meta.get("Sheet") or key.split("::")[0]),
            "Table ID": table_id,
            "Source range": {
                "Start row": table_meta.get("Start row"),
                "End row": table_meta.get("End row"),
                "Header row": table_meta.get("Header row"),
            },
            "Rows": int(len(frame)),
            "Columns": int(len(frame.columns)),
            "Schema hash": schema_hash(frame),
            "Content hash": frame_hash(frame),
            "Candidate grain": grain,
            "Semantic coverage %": round(100.0 * sum(x["Entity"] != "Unknown" for x in fields) / max(1, len(fields)), 1),
            "Status": "Observed",
        })
    return datasets


def build_industrial_semantics(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    frames = result.get("table_datasets") or result.get("cleaned_sheets") or {}
    rows: list[dict[str, Any]] = []
    for key, frame in frames.items():
        for col in frame.columns:
            sem = classify_field(str(col), frame[col])
            rows.append({
                "Dataset key": str(key),
                "Field": str(col),
                **sem,
                "Cardinality": int(frame[col].nunique(dropna=True)),
                "Missing %": round(float(frame[col].isna().mean() * 100.0), 2) if len(frame) else 100.0,
            })
    return rows


def build_contracts(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Generate enforceable dataset contracts with explicit activation policy."""
    datasets = result.get("dataset_registry", [])
    semantics = result.get("industrial_semantics", [])
    by_dataset: dict[str, list[dict[str, Any]]] = {}
    for row in semantics:
        by_dataset.setdefault(str(row.get("Dataset key")), []).append(row)
    contracts: list[dict[str, Any]] = []
    for ds in datasets:
        key = str(ds["Dataset key"])
        fields = by_dataset.get(key, [])
        required = [
            x for x in fields
            if x["Role"] == "Key" and x["Confidence"] >= 0.8
        ]
        rules = [
            {
                "id": "CON-001",
                "name": "Schema present",
                "severity": "High",
                "passed": int(ds["Columns"]) > 0,
                "evidence": f"{ds['Columns']} field(s) discovered.",
            },
            {
                "id": "CON-002",
                "name": "Dataset not empty",
                "severity": "High",
                "passed": int(ds["Rows"]) > 0,
                "evidence": f"{ds['Rows']} row(s) discovered.",
            },
        ]
        frame = (result.get("table_datasets") or result.get("cleaned_sheets") or {}).get(key)
        source_sheet = str(ds.get("Source sheet") or key.split("::")[0])
        if isinstance(frame, pd.DataFrame):
            for item in required:
                series = frame[item["Field"]]
                passed = not bool(series.isna().any())
                rules.append({
                    "id": "CON-REQ-" + _norm(item["Field"])[:16].upper(),
                    "name": f"Required identifier non-null: {item['Field']}",
                    "severity": "High",
                    "passed": passed,
                    "evidence": f"{int(series.isna().sum()):,} missing value(s).",
                })
        inherited = []
        for issue in result.get("validation_results", []):
            if str(issue.get("Sheet", "")) not in {key, source_sheet}:
                continue
            if str(issue.get("Status", "")).upper() == "FAIL":
                inherited.append({
                    "id": "VAL-" + _norm(issue.get("Rule", "validation"))[:24].upper(),
                    "name": str(issue.get("Rule", "Validation rule failed")),
                    "severity": str(issue.get("Severity", "High")),
                    "passed": False,
                    "evidence": str(issue.get("Evidence", "Validation failure detected.")),
                })
        for issue in result.get("engineering_limit_findings", []):
            if str(issue.get("Sheet", "")) in {key, source_sheet}:
                inherited.append({
                    "id": "ENG-" + _norm(issue.get("Field", "limit"))[:20].upper(),
                    "name": str(issue.get("Issue", "Engineering limit violation")),
                    "severity": str(issue.get("Severity", "High")),
                    "passed": False,
                    "evidence": str(issue.get("Evidence", "Engineering limit violation detected.")),
                })
        for issue in result.get("security_scan", []):
            if str(issue.get("Sheet", "")) in {key, source_sheet}:
                inherited.append({
                    "id": "SEC-" + _norm(issue.get("Indicator", "security"))[:20].upper(),
                    "name": "Potential secret/security exposure",
                    "severity": "High",
                    "passed": False,
                    "evidence": f"{issue.get('Indicator', 'security')}: {issue.get('Matches', 0)} match(es).",
                })
        rules.extend(inherited)
        blocked = [r for r in rules if not r["passed"] and str(r["severity"]).casefold() == "high"]
        contract_payload = f"{ds['Dataset ID']}|{key}|{json.dumps(rules, sort_keys=True, default=str)}"
        contract_hash = hashlib.sha256(contract_payload.encode("utf-8")).hexdigest()[:24].upper()
        status = "BLOCKED" if blocked else "PASS"
        contracts.append({
            "Contract ID": "CTR-" + contract_hash[:16],
            "Dataset ID": ds["Dataset ID"],
            "Dataset key": key,
            "Contract version": 1,
            "Contract hash": contract_hash,
            "Status": status,
            "Activation policy": "BLOCK on high-severity failures; explicit exception approval required.",
            "Blocking failures": len(blocked),
            "Rules": rules,
            "Approved exception": False,
            "Approved by": "",
            "Approved at": "",
        })
    return contracts


def contract_map(contracts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(x.get("Dataset key")): x for x in contracts}


def activation_gate(result: Mapping[str, Any], dataset_key: str) -> dict[str, Any]:
    contract = contract_map(list(result.get("dataset_contracts", []))).get(str(dataset_key))
    if not contract:
        return {"allowed": True, "status": "UNCONTRACTED", "reason": "No blocking contract is defined."}
    if contract.get("Status") == "PASS" or contract.get("Approved exception"):
        return {
            "allowed": True,
            "status": "APPROVED",
            "reason": "Contract passed or an explicit exception was approved.",
        }
    return {
        "allowed": False,
        "status": "BLOCKED",
        "reason": f"{int(contract.get('Blocking failures', 0))} high-severity contract failure(s) require review.",
    }


def fidelity_report(raw: bytes, filename: str) -> dict[str, Any]:
    """Inspect workbook/package fidelity risks before generating a data workbook."""
    lower = str(filename).lower()
    report: dict[str, Any] = {
        "File": filename,
        "Source SHA256": hashlib.sha256(raw).hexdigest(),
        "Source format": lower.rsplit(".", 1)[-1].upper() if "." in lower else "UNKNOWN",
        "Preservation mode": "Data-focused governed export",
        "Macro present": False,
        "Charts present": False,
        "Pivot structures present": False,
        "Named ranges present": False,
        "External links present": False,
        "Images present": False,
        "Data validations present": False,
        "Conditional formatting present": False,
        "Fidelity warning": "",
        "Source preserved in evidence package": True,
        "Cleaned export fidelity status": "Data-focused governed export; verify non-tabular workbook features before operational use.",
    }
    if not lower.endswith((".xlsx", ".xlsm")):
        report["Fidelity warning"] = "Delimited text has no workbook presentation layer to preserve."
        return report

    try:
        import openpyxl
        keep_vba = lower.endswith(".xlsm")
        book = openpyxl.load_workbook(io.BytesIO(raw), read_only=False, data_only=False, keep_vba=keep_vba, keep_links=True)
        report["Macro present"] = bool(getattr(book, "vba_archive", None)) if keep_vba else False
        report["Named ranges present"] = bool(list(getattr(book, "defined_names", {}).keys()))
        report["External links present"] = bool(getattr(book, "_external_links", []))
        for ws in book.worksheets:
            report["Charts present"] |= bool(getattr(ws, "_charts", []))
            report["Images present"] |= bool(getattr(ws, "_images", []))
            report["Data validations present"] |= bool(getattr(ws, "data_validations", None) and ws.data_validations.dataValidation)
            report["Conditional formatting present"] |= bool(getattr(ws, "conditional_formatting", None))
        report["Pivot structures present"] = bool(getattr(book, "_pivots", []))
        try:
            book.close()
        except Exception as exc:
            logging.getLogger(__name__).warning("Optional operation failed safely: %s: %s", type(exc).__name__, exc)
    except Exception as exc:
        report["Fidelity warning"] = f"Inspection incomplete: {type(exc).__name__}: {exc}"

    if report["Macro present"] or report["Charts present"] or report["Pivot structures present"] or report["Named ranges present"] or report["External links present"] or report["Images present"]:
        report["Fidelity warning"] = (
            "Source contains workbook features that are inspected but not guaranteed to survive "
            "the governed data export. The original source remains authoritative."
        )
    else:
        report["Fidelity warning"] = "No non-tabular workbook feature requiring special preservation was detected."
    return report


def build_scalable_ingestion_profile(raw: bytes, filename: str) -> dict[str, Any]:
    size = int(len(raw))
    lower = str(filename).lower()
    mode = "chunked-delimited" if lower.endswith((".csv", ".tsv", ".txt")) and size >= 8 * 1024 * 1024 else "bounded-workbook"
    return {
        "File size bytes": size,
        "File size MB": round(size / 1024 / 1024, 2),
        "Mode": mode,
        "Chunk rows": 100_000 if mode == "chunked-delimited" else None,
        "Large file": size >= 25 * 1024 * 1024,
        "Very large file": size >= 100 * 1024 * 1024,
        "Peak-memory strategy": "Chunk parse + concatenate" if mode == "chunked-delimited" else "read-only worksheet iteration",
        "Visualization policy": "Bounded/sample-based rendering for large datasets.",
        "Malformed-row policy": "Fail closed; source records are never silently skipped.",
    }


def scalable_text_reader(raw: bytes, filename: str) -> dict[str, pd.DataFrame]:
    """Chunk-aware reader used by Excel Studio for delimited files."""
    import csv

    text: str | None = None
    encoding = "utf-8-sig"
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            encoding = enc
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("Delimited text encoding could not be decoded safely.")
    if "\\n" in text and "\n" not in text and "\r" not in text:
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n")

    if str(filename).lower().endswith(".tsv"):
        delimiter = "\t"
    else:
        sample_lines = "\n".join(text.splitlines()[:40])
        try:
            delimiter = csv.Sniffer().sniff(sample_lines, delimiters=",;\t|").delimiter
        except Exception:
            delimiter = ","

    # Use Python's csv reader for both small and large inputs. Unlike the
    # pandas C parser, it preserves the earlier Excel Studio contract that
    # irregular-width rows are padded rather than silently discarded or
    # mis-tokenized. Large files are accumulated in bounded row chunks so the
    # downstream dataframe construction remains predictable.
    chunked = len(raw) >= 8 * 1024 * 1024
    chunk_rows = 100_000
    rows = csv.reader(io.StringIO(text), delimiter=delimiter)
    chunks: list[list[list[str]]] = []
    current: list[list[str]] = []
    width = 0
    for row in rows:
        current.append(row)
        width = max(width, len(row))
        if len(current) >= chunk_rows and chunked:
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    if not chunks:
        frame = pd.DataFrame()
    else:
        padded_chunks = [
            pd.DataFrame([r + [""] * (width - len(r)) for r in chunk], dtype=object)
            for chunk in chunks
        ]
        frame = pd.concat(padded_chunks, ignore_index=True) if padded_chunks else pd.DataFrame()
    frame.attrs["source_encoding"] = encoding
    frame.attrs["source_delimiter"] = delimiter
    frame.attrs["ingestion_chunk_rows"] = chunk_rows if chunked else len(frame)
    frame.attrs["source_delimiter"] = delimiter
    return {"CSV" if str(filename).lower().endswith(".csv") else "TEXT": frame}


def build_version_records(result: Mapping[str, Any], prior_versions: list[Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    prior_versions = list(prior_versions or [])
    prior_by_dataset = {str(x.get("Dataset ID")): x for x in prior_versions}
    records = []
    for ds in result.get("dataset_registry", []):
        prior = prior_by_dataset.get(str(ds["Dataset ID"]))
        previous_number = int(prior.get("Version", 0)) if prior else 0
        content_hash = str(ds.get("Content hash", ""))
        recipe = hashlib.sha256(json.dumps(result.get("audits", {}), default=str, sort_keys=True).encode()).hexdigest()[:16]
        version_material = f"{ds['Dataset ID']}|{content_hash}|{recipe}|{result.get('signature','')}"
        version_id = "VER-" + hashlib.sha256(version_material.encode()).hexdigest()[:20].upper()
        records.append({
            "Version ID": version_id,
            "Dataset ID": ds["Dataset ID"],
            "Dataset key": ds["Dataset key"],
            "Version": (previous_number + 1) if prior and content_hash != str(prior.get("Content hash", "")) else (previous_number if prior else 1),
            "Created UTC": _iso(),
            "Source SHA256": result.get("signature", ""),
            "Schema hash": ds.get("Schema hash", ""),
            "Content hash": content_hash,
            "Recipe hash": recipe,
            "Rows": ds.get("Rows", 0),
            "Columns": ds.get("Columns", 0),
            "Immutable manifest": True,
        })
    return records



def refresh_version_state(result: dict[str, Any], prior_versions: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Recompute the dataset-first registry and immutable version manifests after edits."""
    result["dataset_registry"] = build_dataset_registry(result)
    history = list(prior_versions if prior_versions is not None else result.get("dataset_versions_history", []))
    records = build_version_records(result, history)
    existing_ids = {str(x.get("Version ID")) for x in history}
    result["dataset_versions"] = [x for x in records if str(x.get("Version ID")) not in existing_ids] or records
    merged = history + result["dataset_versions"]
    unique: dict[str, dict[str, Any]] = {}
    for item in merged:
        unique[str(item.get("Version ID"))] = item
    result["dataset_versions_history"] = list(unique.values())[-200:]
    result["dataset_version"] = max([int(x.get("Version", 1)) for x in result["dataset_versions_history"]] or [1])
    result["lineage_manifest"] = {
        **dict(result.get("lineage_manifest", {})),
        "datasets": result["dataset_registry"],
        "versions": result["dataset_versions_history"],
        "latest_version_ids": [x["Version ID"] for x in result["dataset_versions"]],
        "foundation_version": FOUNDATION_VERSION,
    }
    return result


def augment_evidence_bundle(result: dict[str, Any], raw: bytes, filename: str) -> bytes:
    """Add the exact source bytes plus machine-readable governance evidence."""
    existing = result.get("bundle", b"")
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(existing), "r") as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item.filename))
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(filename)).strip("_") or "source_file"
        dst.writestr("SOURCE_ORIGINAL/" + safe_name, raw)
        evidence = {
            "foundation_version": FOUNDATION_VERSION,
            "dataset_registry": result.get("dataset_registry", []),
            "dataset_contracts": result.get("dataset_contracts", []),
            "fidelity_report": result.get("fidelity_report", {}),
            "scalable_ingestion": result.get("scalable_ingestion", {}),
            "dataset_versions": result.get("dataset_versions_history", []),
            "industrial_semantics": result.get("industrial_semantics", []),
        }
        dst.writestr("governance/foundation_manifest.json", json.dumps(evidence, indent=2, ensure_ascii=False, default=str))
    return out.getvalue()


def persist_versions(username: str, result: dict[str, Any], workspace: str = "default") -> list[dict[str, Any]]:
    """Persist immutable version manifests using Shoir-IE's existing durable artifact store."""
    refresh_version_state(result)
    records = list(result.get("dataset_versions", []))
    if not username or not records:
        return records
    try:
        from shoir_enterprise_layer import record_artifact
        for rec in records:
            aid = rec["Version ID"]
            record_artifact(
                username,
                "excel_dataset_version",
                f"{rec['Dataset ID']}:{rec['Version']}",
                rec,
                workspace,
                artifact_id=aid,
            )
        result["_durable_version_status"] = "persisted"
    except Exception as exc:
        result["_durable_version_status"] = f"unavailable: {type(exc).__name__}"
    return records


def enrich_result(result: dict[str, Any], raw: bytes, filename: str) -> dict[str, Any]:
    result["foundation_version"] = FOUNDATION_VERSION
    result["dataset_registry"] = build_dataset_registry(result)
    result["industrial_semantics"] = build_industrial_semantics(result)
    result["dataset_contracts"] = build_contracts(result)
    result["activation_gate_by_dataset"] = {
        x["Dataset key"]: activation_gate(
            {"dataset_contracts": result["dataset_contracts"]},
            x["Dataset key"],
        )
        for x in result["dataset_registry"]
    }
    result["fidelity_report"] = fidelity_report(raw, filename)
    result["scalable_ingestion"] = build_scalable_ingestion_profile(raw, filename)
    result["dataset_versions"] = build_version_records(result, result.get("dataset_versions_history", []))
    result["dataset_version"] = max([int(x.get("Version", 1)) for x in result["dataset_versions"]] or [1])
    result["dataset_versions_history"] = list(result.get("dataset_versions_history", [])) + result["dataset_versions"]
    # De-duplicate deterministic versions so reruns do not create duplicate history rows.
    result["dataset_versions_history"] = list({str(x["Version ID"]): x for x in result["dataset_versions_history"]}.values())[-200:]
    result["lineage_manifest"] = {
        **dict(result.get("lineage_manifest", {})),
        "foundation_version": FOUNDATION_VERSION,
        "datasets": result["dataset_registry"],
        "contracts": [
            {
                "Dataset ID": x["Dataset ID"],
                "Contract version": x["Contract version"],
                "Status": x["Status"],
                "Blocking failures": x["Blocking failures"],
            }
            for x in result["dataset_contracts"]
        ],
        "fidelity": result["fidelity_report"],
        "scalability": result["scalable_ingestion"],
        "versions": result["dataset_versions"],
    }
    return result


def approve_contract_exception(result: dict[str, Any], dataset_key: str, username: str) -> bool:
    contracts = result.get("dataset_contracts", [])
    for contract in contracts:
        if str(contract.get("Dataset key")) == str(dataset_key):
            contract["Approved exception"] = True
            contract["Approved by"] = str(username)
            contract["Approved at"] = _iso()
            contract["Status"] = "APPROVED EXCEPTION"
            result.setdefault("contract_approval_log", []).append({
                "Dataset key": dataset_key,
                "Dataset ID": contract.get("Dataset ID"),
                "Reviewer": username,
                "Approved UTC": contract["Approved at"],
                "Reason": "Explicit analyst exception approval.",
            })
            result["activation_gate_by_dataset"] = {
                x["Dataset key"]: activation_gate(
                    {"dataset_contracts": contracts},
                    x["Dataset key"],
                )
                for x in result.get("dataset_registry", [])
            }
            return True
    return False
