"""Deterministic guided-study, contextual-help and practice engines for T002/T010/T089.

These helpers organize steps and check explicitly supported worked examples. They do not
fabricate measurements, run unsupported specialist calculations, or claim outcomes.
"""
from __future__ import annotations

import math
from typing import Any

_STUDY_TEMPLATES = {
    "Production capacity / bottleneck": {
        "objective_default": "Identify the limiting production step and quantify a capacity gap.",
        "tools": ["T011", "T013", "T023", "T025", "T073", "T095"],
        "required": ["demand and period", "net available time and unit", "measured cycle time or throughput per step", "planned downtime/yield definitions"],
        "steps": [
            ("Validate source data and periods", "Check column types, missingness, units and time scope.", "T011"),
            ("Profile data quality", "Review duplicate/missing values and confirm measurement definitions.", "T013"),
            ("Calculate demand-aligned takt/capacity", "Use the same production period for available time and demand.", "T023"),
            ("Analyze the constraint", "Use comparable cycle-time or measured-throughput observations; label inference separately.", "T025"),
            ("Compare explicit alternatives", "Change only stated scenario inputs and rerun the same KPI definitions.", "T073"),
            ("Document the decision", "Export methods, units, evidence references and limitations.", "T095"),
        ],
    },
    "Quality / defects": {
        "objective_default": "Understand a defect trend and select a validated improvement test.",
        "tools": ["T011", "T013", "T028", "T031", "T032", "T039", "T083", "T095"],
        "required": ["defect counts and denominator", "measurement period and product/process scope", "specification limits if capability is assessed", "baseline and post-change evidence if ROI is claimed"],
        "steps": [
            ("Validate defect data and denominator", "Do not combine unlike periods, products or exposure denominators.", "T011"),
            ("Profile missingness and duplicates", "Resolve data issues before using a defect rate.", "T013"),
            ("Explore causes without assuming causality", "Pareto ranks observed categories; it does not prove the cause.", "T028"),
            ("Select an appropriate quality method", "Choose a control chart or capability method only when its assumptions and limits apply.", "T031"),
            ("Record corrective action", "Keep owner, due date and effectiveness evidence separate.", "T039"),
            ("Export the method and evidence", "Clearly distinguish estimates from independently verified outcomes.", "T095"),
        ],
    },
    "Facility layout / material flow": {
        "objective_default": "Compare facility layout alternatives using explicit flow and distance inputs.",
        "tools": ["T011", "T013", "T065", "T073", "T095"],
        "required": ["complete department/area list", "from-to flow matrix with known units and period", "distance or adjacency assumptions", "handling-cost definition if cost is compared"],
        "steps": [
            ("Validate the department list", "Confirm each area has a stable identifier and every flow endpoint exists.", "T011"),
            ("Profile and reconcile flows", "Resolve missing, duplicate and unmatched department references.", "T013"),
            ("Build the facility/SLP alternative", "Review relationship weights, heatmap and flow-distance assumptions.", "T065"),
            ("Compare alternatives", "Use consistent departments, flow period and distance/cost definitions.", "T073"),
            ("Export evidence", "Include matrices, assumptions, method version and known limitations.", "T095"),
        ],
    },
    "Maintenance / reliability": {
        "objective_default": "Prioritize maintenance work using explicit asset and failure evidence.",
        "tools": ["T011", "T013", "T041", "T042", "T043", "T049", "T095"],
        "required": ["asset IDs and observation window", "failure/repair timestamps or operating hours", "work orders, skills and downtime windows if backlog is optimized", "criticality and due-date definitions"],
        "steps": [
            ("Validate asset and event identities", "Check missing IDs, ordered timestamps and observation boundaries.", "T011"),
            ("Review data quality", "Resolve duplicates and incomplete failure/repair intervals.", "T013"),
            ("Choose the reliability method", "Match the method to uncensored/censored observations and state its assumptions.", "T041"),
            ("Summarize recorded reliability", "Use only complete eligible operating/failure/repair intervals.", "T042"),
            ("Plan maintenance work", "Provide skills, capacity and windows; inspect work orders that remain unscheduled.", "T049"),
            ("Export actions and evidence", "Keep estimated exposure separate from observed outcomes.", "T095"),
        ],
    },
    "Inventory / supply planning": {
        "objective_default": "Review supply coverage and inventory choices under visible demand assumptions.",
        "tools": ["T011", "T013", "T054", "T055", "T056", "T058", "T073", "T095"],
        "required": ["dated demand history or explicit demand plan", "inventory/on-order quantities", "lead time and lot-size rules", "validated bill of materials when material requirements are calculated"],
        "steps": [
            ("Validate demand and item master", "Reconcile identifiers, dates, units and duplicate records.", "T011"),
            ("Profile the input data", "Check missing values, errant units and duplicate item-periods.", "T013"),
            ("Select a method", "Use inventory policy, ABC/XYZ or material requirements only with its required inputs.", "T055"),
            ("Compare supply and scenarios", "Show the assumed demand, lead time, service level and cost basis.", "T073"),
            ("Record supplier evidence", "Expose weights, missing evidence and scoring assumptions.", "T058"),
            ("Export the decision basis", "Preserve source dates, inputs and caveats.", "T095"),
        ],
    },
    "Research / statistical study": {
        "objective_default": "Plan an explainable statistical study and preserve reproducibility metadata.",
        "tools": ["T011", "T013", "T035", "T036", "T037", "T085", "T087", "T090"],
        "required": ["research question and primary outcome", "sampling unit and study design", "supported method and assumptions", "dataset fingerprint and source references"],
        "steps": [
            ("Validate and profile the dataset", "Confirm types, missingness, duplicates and sampling unit.", "T011"),
            ("Choose supported methods", "Record hypotheses, model assumptions and a defensible analysis plan.", "T036"),
            ("Plan power where applicable", "State effect size, alpha, target power and supported design.", "T085"),
            ("Run and diagnose the selected method", "Report assumptions, uncertainty and limitations; do not invent unsupported tests.", "T037"),
            ("Record reproducibility metadata", "Package versions, seed and fingerprints only; do not include secrets/raw data in the metadata-only pack.", "T087"),
            ("Build a methods report", "References and review labels are not independently authenticated by the report builder.", "T090"),
        ],
    },
}

_HELP_ARTICLES = [
    {"topic":"Data import and quality","terms":["data","import","workbook","excel","csv","missing","duplicate","mapping"],
     "summary":"Start with a source-preserving preview. Confirm sheet names, row counts, keys, types, units, time scope and missingness before transformations.",
     "steps":["Keep the original input unchanged until the proposed operation is reviewed.","Resolve duplicate keys and check join cardinality before merging.","Record mappings and transformation assumptions; inspect the result row count."],
     "related_tools":["T011","T012","T013","T014","T015","T020"],"caveat":"A successful parser does not prove that mapped fields have the correct business meaning or units."},
    {"topic":"Takt, capacity and bottlenecks","terms":["takt","capacity","bottleneck","throughput","cycle","production","line"],
     "summary":"Takt is net available production time divided by demand for the same period. A bottleneck claim requires comparable measured cycle-time or throughput data.",
     "steps":["Confirm one consistent time unit and production period.","Calculate demand-aligned takt/capacity.","Check measured cycle times, downtime/yield and resource constraints before interpreting a limiting step."],
     "related_tools":["T023","T024","T025","T026","T053"],"caveat":"Theoretical capacity excludes losses and constraints unless they are explicitly modeled."},
    {"topic":"Quality and process capability","terms":["quality","oee","spc","control chart","cpk","capability","defect","fmea","capa"],
     "summary":"Use control limits to assess process behavior and specification limits to assess customer requirements; they are not interchangeable.",
     "steps":["Validate the measurement system and sampling design.","Choose a chart/statistical method that matches the data.","Record specification limits, subgroup choices and distribution assumptions.","Treat Pareto/root-cause outputs as investigation aids, not causality proof."],
     "related_tools":["T026","T028","T031","T032","T033","T038","T039"],"caveat":"A capability index is only meaningful when the data and assumptions fit the selected method."},
    {"topic":"Facility layout and flow","terms":["facility","layout","slp","from-to","flow","distance","warehouse"],
     "summary":"Layout comparison depends on a complete area list, a validated from-to matrix and a clear distance/handling-cost definition.",
     "steps":["Use stable department IDs and confirm all matrix endpoints.","Review relationship chart/weights and missing flows.","Compare alternatives on the same flows, units and cost basis.","Export the assumptions with the result."],
     "related_tools":["T059","T065"],"caveat":"A layout score is not an implementation-ready design unless constraints and site requirements are reviewed."},
    {"topic":"Reliability and maintenance","terms":["reliability","mtbf","mttr","weibull","maintenance","anomaly","asset","failure"],
     "summary":"Reliability methods depend on a defined observation window and explicit treatment of failures, repairs and censored observations.",
     "steps":["Validate asset IDs and event timestamps.","Check incomplete intervals and unit definitions.","Inspect fit diagnostics and method warnings.","Review any anomaly flags with calibration and maintenance context."],
     "related_tools":["T041","T042","T043","T048","T049"],"caveat":"An anomaly flag does not diagnose a physical fault or establish its cause."},
    {"topic":"Research, power and reproducibility","terms":["research","power","sample size","hypothesis","study","reproducibility","report","statistics"],
     "summary":"A credible study states its question, design, method, assumptions, data provenance, uncertainty and limits.",
     "steps":["Identify the experimental/sampling unit and primary outcome.","Choose only a supported test/design and validate its assumptions.","Record effect size and planning assumptions before using sample-size results.","Retain source fingerprint, seed and method version for traceability."],
     "related_tools":["T035","T036","T037","T085","T086","T087","T090"],"caveat":"Planning estimates do not guarantee valid inference; metadata checksums do not authenticate sources."},
    {"topic":"Economics, sustainability and ROI","terms":["npv","irr","roi","savings","energy","water","waste","carbon","cost"],
     "summary":"State the currency, period, discount rate, normalized denominator and factor provenance. Keep estimated benefit separate from measured, verified benefit.",
     "steps":["Record baseline, post-intervention period and comparability rules.","Name and date any tariff/emissions factors.","Include implementation costs where appropriate.","Label estimates and user-entered review claims; do not represent them as independently verified savings."],
     "related_tools":["T077","T078","T079","T081","T082","T083"],"caveat":"Synthetic data and modeled savings are not customer results or audited environmental disclosures."},
    {"topic":"Simulation and scenario analysis","terms":["simulation","monte carlo","scenario","digital twin","uncertainty","disruption"],
     "summary":"Simulation outputs are conditional on the event logic, input distributions, constraints and calibration evidence.",
     "steps":["Write down the process and entity/resource logic.","Validate distributions, units and arrival/service assumptions.","Set a reproducible seed and enough replications for the intended comparison.","Compare against observed data before making operational claims."],
     "related_tools":["T071","T072","T073","T074","T075","T080"],"caveat":"A simulated scenario is not a live controller or a calibrated digital twin without data/configuration evidence."},
]

_PRACTICE_QUESTIONS = {
    "Takt time": {
        "question_id":"PRACTICE-TAKT-001",
        "prompt":"A line has 480 net available minutes in a shift and demand is 400 units in that same shift. What is takt time in minutes per unit?",
        "correct_answer":1.2,
        "tolerance":0.001,
        "unit":"minutes/unit",
        "formula":"Takt time = net available time / demand = 480 min / 400 units = 1.2 min/unit.",
        "steps":["Check that available time and demand refer to the same production period.","Divide net available time by demand.","Report the result as minutes per unit."],
        "related_tool":"T023",
    },
    "OEE": {
        "question_id":"PRACTICE-OEE-001",
        "prompt":"Availability is 90%, performance is 95% and quality is 98%. What is OEE as a percentage?",
        "correct_answer":83.79,
        "tolerance":0.01,
        "unit":"%",
        "formula":"OEE = availability × performance × quality = 0.90 × 0.95 × 0.98 × 100% = 83.79%.",
        "steps":["Convert each percentage to a proportion.","Multiply availability, performance and quality once each.","Convert the resulting proportion back to percent."],
        "related_tool":"T026",
    },
    "Standard time": {
        "question_id":"PRACTICE-STANDARD-TIME-001",
        "prompt":"Observed times are 0.50, 0.60 and 0.55 minutes. Performance rating is 110%. Allowance is 15% of normal time. What is standard time in minutes per cycle?",
        "correct_answer":0.69575,
        "tolerance":0.005,
        "unit":"minutes/cycle",
        "formula":"Observed mean = 0.55 min; normal time = 0.55 × 1.10 = 0.605 min; standard time = 0.605 × (1 + 0.15) = 0.69575 min.",
        "steps":["Calculate the mean observed time: (0.50 + 0.60 + 0.55) / 3 = 0.55 min.","Apply the 110% rating: 0.55 × 1.10 = 0.605 min normal time.","Since allowance is 15% of normal time, standard time = 0.605 × 1.15 = 0.69575 min."],
        "related_tool":"T021",
    },
}


def build_guided_study_plan(
    *, problem_type: str, objective: str = "", data_state: str = "No validated dataset",
    key_constraints: str = "", available_fields: list[str] | None = None,
) -> dict[str, Any]:
    kind = str(problem_type or "").strip()
    if kind not in _STUDY_TEMPLATES:
        raise ValueError(f"Problem type must be one of: {', '.join(_STUDY_TEMPLATES)}.")
    state = str(data_state or "").strip()
    allowed_states = {"No validated dataset", "Imported but not validated", "Validated dataset", "Measured baseline reviewed"}
    if state not in allowed_states:
        raise ValueError(f"Data state must be one of: {', '.join(sorted(allowed_states))}.")
    obj = str(objective or "").strip()
    if len(obj) > 1000:
        raise ValueError("Objective is limited to 1000 characters.")
    constraints = str(key_constraints or "").strip()
    if len(constraints) > 2000:
        raise ValueError("Key constraints are limited to 2000 characters.")
    fields = [str(v).strip() for v in (available_fields or []) if str(v).strip()]
    if len(fields) > 100:
        raise ValueError("Enter no more than 100 available field names.")
    template = _STUDY_TEMPLATES[kind]
    missing = list(template["required"])
    if state == "No validated dataset":
        missing.insert(0, "approved source dataset or documented manual observations")
    elif state == "Imported but not validated":
        missing.insert(0, "completed import/profile/schema and unit validation")
    if not obj:
        missing.insert(0, "specific decision question or improvement objective")
    steps = [
        {"step":i+1,"action":action,"why":why,"recommended_tool_id":tool_id,"expected_output":"A reviewable result with assumptions, units, warnings and source provenance."}
        for i,(action,why,tool_id) in enumerate(template["steps"])
    ]
    return {
        "tool_id":"T002","status":"PLAN_GENERATED","method":"Curated deterministic industrial-engineering workflow templates",
        "problem_type":kind,"objective":obj or template["objective_default"],"data_state":state,
        "key_constraints":constraints,"available_fields":fields,"recommended_tool_ids":template["tools"],
        "missing_inputs":missing,"steps":steps,
        "assumptions":["The plan is a checklist, not a calculation or an execution of the recommended tools.",
                       "The user must confirm that each method matches the actual data and engineering question.",
                       "Recommended target IDs can have different subscription requirements and readiness status."],
        "warnings":["No plant result, saving, bottleneck or engineering decision was calculated by this wizard.",
                    "Do not run a later step until required inputs, method assumptions and units are validated."],
        "metrics":{"step_count":len(steps),"recommended_tool_count":len(template["tools"]),"missing_input_count":len(missing),
                   "ready_to_analyze":bool(state in {"Validated dataset","Measured baseline reviewed"} and obj and not missing)},
    }


def search_contextual_help(*, query: str = "", tool_id: str = "") -> dict[str, Any]:
    q = str(query or "").strip().casefold()
    canonical_id = str(tool_id or "").strip().upper()
    if len(q) > 300:
        raise ValueError("Help search is limited to 300 characters.")
    if canonical_id and (len(canonical_id) != 4 or not canonical_id.startswith("T") or not canonical_id[1:].isdigit() or not 1 <= int(canonical_id[1:]) <= 100):
        raise ValueError("Tool ID must be a canonical target ID from T001 to T100.")
    if not q and not canonical_id:
        raise ValueError("Enter a help topic or choose a canonical tool ID.")
    matches = []
    for article in _HELP_ARTICLES:
        related = article["related_tools"]
        terms = [article["topic"], *article["terms"], *related]
        score = sum(1 for term in terms if (term.casefold() in q if q else False))
        if q and any(token for token in q.split() if any(token in term.casefold() for term in terms)):
            score = max(score, 1)
        if canonical_id and canonical_id in related:
            score += 10
        if score:
            matches.append((score, article))
    matches.sort(key=lambda x: (-x[0], x[1]["topic"]))
    articles = [{k:v for k,v in article.items() if k not in {"terms"}} for _,article in matches[:8]]
    return {
        "tool_id":"T010","status":"HELP_RESULTS","method":"Curated contextual help with canonical target references",
        "query":q,"selected_tool_id":canonical_id,"articles":articles,
        "metrics":{"result_count":len(articles),"matched_tool_id":any(canonical_id in a["related_tools"] for a in articles) if canonical_id else False},
        "warnings":["Help describes method scope and prerequisites; it does not run the linked calculation.",
                    "Use the linked target's actual readiness and tier information before execution."],
    }


def get_practice_question(*, topic: str) -> dict[str, Any]:
    key = str(topic or "").strip()
    if key not in _PRACTICE_QUESTIONS:
        raise ValueError(f"Topic must be one of: {', '.join(_PRACTICE_QUESTIONS)}.")
    question = _PRACTICE_QUESTIONS[key]
    return {
        "tool_id":"T089","status":"QUESTION_READY","method":"Fixed, deterministic worked-example bank with checked arithmetic",
        "topic":key,"question_id":question["question_id"],"prompt":question["prompt"],
        "unit":question["unit"],"related_tool_id":question["related_tool"],
        "assumptions":["The exercise values are illustrative and must not be treated as plant observations.",
                       "The answer is conditional on the stated formula and unit/allowance convention."],
        "metrics":{"question_count":len(_PRACTICE_QUESTIONS),"answer_required":True},
    }


def check_practice_answer(*, topic: str, answer: float) -> dict[str, Any]:
    key = str(topic or "").strip()
    if key not in _PRACTICE_QUESTIONS:
        raise ValueError(f"Topic must be one of: {', '.join(_PRACTICE_QUESTIONS)}.")
    if isinstance(answer, bool):
        raise ValueError("Answer must be a finite number.")
    try:
        value = float(answer)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Answer must be a finite number.") from exc
    if not math.isfinite(value):
        raise ValueError("Answer must be a finite number.")
    question = _PRACTICE_QUESTIONS[key]
    correct = math.isclose(value, question["correct_answer"], rel_tol=0.0, abs_tol=question["tolerance"])
    return {
        "tool_id":"T089","status":"ANSWER_CHECKED","method":"Deterministic numeric answer comparison with stated tolerance",
        "topic":key,"question_id":question["question_id"],"user_answer":value,
        "correct_answer":question["correct_answer"],"unit":question["unit"],"is_correct":bool(correct),
        "worked_formula":question["formula"],"solution_steps":question["steps"],
        "assumptions":["The stated problem and unit convention are authoritative for this exercise.",
                       "Tolerance handles rounding only; it does not accommodate a different method or unit."],
        "warnings":["Correctness applies only to this worked-example question. It is not an independent engineering review."],
        "metrics":{"is_correct":bool(correct),"absolute_error":abs(value-question["correct_answer"]),
                   "accepted_absolute_tolerance":question["tolerance"]},
    }
