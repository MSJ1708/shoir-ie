"""Structured technical methods/report builder for Research Pack target T090."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import re
from typing import Any, Sequence


def _field(value: Any, label: str, *, required: bool=False, maximum: int=12000) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{label} is required.")
    if len(text) > maximum:
        raise ValueError(f"{label} exceeds the {maximum}-character limit.")
    if "\x00" in text:
        raise ValueError(f"{label} contains an invalid null character.")
    return text


def _list(values: Sequence[Any] | None, label: str, *, maximum_items: int=100) -> list[str]:
    result=[]
    for ix, raw in enumerate(values or [], start=1):
        item=_field(raw, f"{label} item {ix}", required=True, maximum=3000)
        result.append(item)
    if len(result)>maximum_items:
        raise ValueError(f"{label} is limited to {maximum_items} items.")
    return result


def build_research_methods_report(
    *,
    title: str,
    authors_or_team: str,
    purpose: str,
    method_name: str,
    method_version: str,
    dataset_description: str,
    dataset_fingerprint: str = "",
    input_scope: str = "",
    formula_or_equations: str = "",
    parameters: str = "",
    assumptions: Sequence[Any] | None = None,
    results_summary: str = "",
    uncertainty_or_diagnostics: str = "",
    limitations: Sequence[Any] | None = None,
    source_references: Sequence[Any] | None = None,
    random_seed: str = "",
    environment_note: str = "",
    review_status: str = "DRAFT — NOT INDEPENDENTLY REVIEWED",
    created_at: str | None = None,
) -> dict[str, Any]:
    title=_field(title,"Title",required=True,maximum=300)
    authors=_field(authors_or_team,"Authors / team",maximum=500)
    purpose=_field(purpose,"Purpose",required=True,maximum=5000)
    method=_field(method_name,"Method name",required=True,maximum=500)
    version=_field(method_version,"Method version",required=True,maximum=200)
    dataset=_field(dataset_description,"Dataset description",required=True,maximum=5000)
    fingerprint=_field(dataset_fingerprint,"Dataset fingerprint",maximum=200).lower()
    if fingerprint and not re.fullmatch(r"[0-9a-f]{64}",fingerprint):
        raise ValueError("Dataset fingerprint must be blank or a 64-character SHA-256 hex digest.")
    formula=_field(formula_or_equations,"Formula/equations",maximum=12000)
    params=_field(parameters,"Parameters",maximum=8000)
    result=_field(results_summary,"Results summary",required=True,maximum=10000)
    uncertainty=_field(uncertainty_or_diagnostics,"Uncertainty/diagnostics",maximum=8000)
    input_scope=_field(input_scope,"Input scope",maximum=3000)
    seed=_field(random_seed,"Random seed",maximum=200)
    environment=_field(environment_note,"Environment note",maximum=3000)
    allowed={"DRAFT — NOT INDEPENDENTLY REVIEWED","REVIEW REQUESTED","REVIEWED BY AUTHOR","INDEPENDENT REVIEW REPORTED BY USER"}
    review=_field(review_status,"Review status",required=True,maximum=100)
    if review not in allowed:
        raise ValueError("Review status must be one of the listed draft/user-reported states.")
    assumption_list=_list(assumptions,"Assumptions")
    limitation_list=_list(limitations,"Limitations")
    reference_list=_list(source_references,"Source references")
    if created_at:
        try:
            created=datetime.fromisoformat(str(created_at).replace("Z","+00:00"))
        except ValueError as exc:
            raise ValueError("Created-at time must be ISO-8601.") from exc
        if created.tzinfo is None:
            raise ValueError("Created-at time must include a timezone.")
        created_utc=created.astimezone(timezone.utc).isoformat()
    else:
        created_utc=datetime.now(timezone.utc).isoformat()

    def section(title: str, body: str) -> str:
        return f"## {title}\n\n{body.strip() if body.strip() else '_Not supplied._'}\n"
    report_parts=[
        f"# {title}\n\n**Status:** {review}  \n**Prepared (UTC):** {created_utc}  \n**Authors/team:** {authors or 'Not supplied'}",
        section("Purpose and research question",purpose),
        section("Method and version",f"**Method:** {method}\n\n**Method version:** {version}"),
        section("Dataset and provenance",f"**Description:** {dataset}\n\n**Input scope:** {input_scope or 'Not supplied'}\n\n**Dataset SHA-256:** {fingerprint or 'Not supplied'}\n\nRaw dataset content is not included in this report builder output."),
        section("Formulae and equations",formula),
        section("Parameters and configuration",params),
        section("Assumptions","\n".join(f"- {item}" for item in assumption_list) if assumption_list else ""),
        section("Results summary",result),
        section("Uncertainty and diagnostics",uncertainty),
        section("Limitations","\n".join(f"- {item}" for item in limitation_list) if limitation_list else ""),
        section("Source references","\n".join(f"- {item}" for item in reference_list) if reference_list else ""),
        section("Reproducibility metadata",f"**Random seed:** {seed or 'Not supplied'}\n\n**Environment note:** {environment or 'Not supplied'}"),
        "## Interpretation and review\n\nThis report is a structured rendering of user-supplied methods, results and references. It does not independently validate calculations, authenticate source documents, verify citations, or constitute professional/legal/safety approval. Review the method, data comparability, assumptions and limitations before relying on the findings.\n",
    ]
    report="\n\n".join(report_parts).strip()+"\n"
    digest=hashlib.sha256(report.encode("utf-8")).hexdigest()
    return {
        "tool_id":"T090","status":"REPORT_GENERATED",
        "report_markdown":report,
        "file_name":re.sub(r"[^A-Za-z0-9_-]+","_",title).strip("_")[:80] or "shoir_ie_research_report",
        "sha256":digest,
        "byte_count":len(report.encode("utf-8")),
        "created_at_utc":created_utc,
        "review_status":review,
        "source_reference_count":len(reference_list),
        "raw_dataset_included":False,
        "metrics":{"report_sections":12,"source_reference_count":len(reference_list),"assumption_count":len(assumption_list),
                   "limitation_count":len(limitation_list),"byte_count":len(report.encode("utf-8")),"sha256":digest},
        "warnings":[
            "References and results are user supplied and have not been independently authenticated.",
            "The report is Markdown, not a digitally signed or peer-reviewed publication.",
            "Raw dataset cells are not attached; use authorized data workflows and compare the stated fingerprint where available.",
        ],
    }
