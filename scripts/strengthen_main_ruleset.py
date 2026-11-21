#!/usr/bin/env python3
"""Safely strengthen the Shoir-IE main-branch GitHub ruleset.

This tool is intentionally dry-run by default. Run with --apply from an
administrator-authenticated GitHub CLI session with repository Administration
write permission. It updates only the existing required_status_checks list;
all other ruleset conditions, rules, review requirements and bypass settings
are preserved. It never changes the staging ruleset.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any


REPOSITORY = "MSJ1708/shoir-ie"
RULESET_ID = 26065188
API_PATH = f"repos/{REPOSITORY}/rulesets/{RULESET_ID}"
REQUIRED_CONTEXTS = (
    "test",
    "edge-function",
    "engine-regression",
    "security-quality",
    "clean-postgres-migration-replay",
    "postgres-transaction-contract",
    "production-v9-security-backport",
    "excel-intelligence",
)
PAYLOAD_KEYS = ("name", "target", "enforcement", "bypass_actors", "conditions", "rules")


class RulesetError(RuntimeError):
    """The live ruleset does not match the safe update preconditions."""


def validate_safe_preconditions(ruleset: dict[str, Any]) -> dict[str, Any]:
    """Return the existing required-status-check rule after verifying invariants."""
    if ruleset.get("id") != RULESET_ID:
        raise RulesetError("GitHub returned an unexpected ruleset ID; refusing to modify it.")
    if ruleset.get("name") != "Protect main — release gates":
        raise RulesetError("The main ruleset name differs from the expected protected ruleset.")
    if ruleset.get("target") != "branch" or ruleset.get("enforcement") != "active":
        raise RulesetError("The main ruleset is not an active branch ruleset.")
    if ruleset.get("bypass_actors") != []:
        raise RulesetError("The main ruleset has bypass actors or its bypass state is not verifiably empty.")

    conditions = ruleset.get("conditions")
    ref_name = conditions.get("ref_name") if isinstance(conditions, dict) else None
    include = ref_name.get("include") if isinstance(ref_name, dict) else None
    if not isinstance(include, list) or "~DEFAULT_BRANCH" not in include:
        raise RulesetError("The ruleset no longer targets the default branch exactly; manual review is required.")

    rules = ruleset.get("rules")
    if not isinstance(rules, list):
        raise RulesetError("The ruleset rule collection is malformed.")

    pr_rule = next((rule for rule in rules if isinstance(rule, dict) and rule.get("type") == "pull_request"), None)
    if not isinstance(pr_rule, dict) or not isinstance(pr_rule.get("parameters"), dict):
        raise RulesetError("The pull-request review rule is missing or malformed.")
    pr = pr_rule["parameters"]
    if (
        not isinstance(pr.get("required_approving_review_count"), int)
        or pr["required_approving_review_count"] < 1
        or pr.get("require_last_push_approval") is not True
        or pr.get("required_review_thread_resolution") is not True
    ):
        raise RulesetError("Existing independent-review protections are not intact; refusing to modify the ruleset.")

    check_rule = next((rule for rule in rules if isinstance(rule, dict) and rule.get("type") == "required_status_checks"), None)
    if not isinstance(check_rule, dict) or not isinstance(check_rule.get("parameters"), dict):
        raise RulesetError("The existing required-status-check rule is missing or malformed.")
    params = check_rule["parameters"]
    if params.get("strict_required_status_checks_policy") is not True:
        raise RulesetError("Strict required-status-check policy is not enabled; manual review is required.")
    checks = params.get("required_status_checks")
    if not isinstance(checks, list):
        raise RulesetError("The required status-check collection is malformed.")

    seen: set[str] = set()
    for item in checks:
        if not isinstance(item, dict) or not isinstance(item.get("context"), str) or not item["context"]:
            raise RulesetError("A required status-check entry is malformed.")
        if item["context"] in seen:
            raise RulesetError("Duplicate required status-check contexts exist; manual review is required.")
        seen.add(item["context"])
    return check_rule


def build_updated_payload(ruleset: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Add only missing main CI contexts and preserve all other ruleset fields."""
    check_rule = validate_safe_preconditions(ruleset)
    params = check_rule["parameters"]
    checks = [dict(item) for item in params["required_status_checks"]]
    current_contexts = {item["context"] for item in checks}
    missing = [context for context in REQUIRED_CONTEXTS if context not in current_contexts]

    # Preserve the GitHub Actions integration binding already used by the
    # existing main checks. Do not guess a new integration or weaken provenance.
    integration_id = next(
        (item.get("integration_id") for item in checks if item["context"] == "test" and "integration_id" in item),
        None,
    )
    if integration_id is None:
        integration_id = next((item.get("integration_id") for item in checks if "integration_id" in item), None)

    for context in missing:
        entry: dict[str, Any] = {"context": context}
        if integration_id is not None:
            entry["integration_id"] = integration_id
        checks.append(entry)

    params["required_status_checks"] = checks
    payload = {key: ruleset[key] for key in PAYLOAD_KEYS if key in ruleset}
    if set(payload) != set(PAYLOAD_KEYS):
        raise RulesetError("The live ruleset is missing a required update field; refusing a partial replacement.")
    return payload, missing


def verify_updated_ruleset(ruleset: dict[str, Any]) -> None:
    """Ensure all eight contexts and original review/bypass protections remain."""
    check_rule = validate_safe_preconditions(ruleset)
    contexts = {item["context"] for item in check_rule["parameters"]["required_status_checks"]}
    missing = sorted(set(REQUIRED_CONTEXTS) - contexts)
    if missing:
        raise RulesetError("Post-update verification is missing required contexts: " + ", ".join(missing))


def _gh_api(method: str, input_json: str | None = None) -> dict[str, Any]:
    command = ["gh", "api"]
    if method != "GET":
        command.extend(["--method", method, API_PATH, "--input", "-"])
    else:
        command.append(API_PATH)
    try:
        result = subprocess.run(
            command,
            input=input_json,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise RulesetError("GitHub CLI (gh) is not installed on this computer.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RulesetError("GitHub CLI request timed out; no completion is claimed.") from exc
    if result.returncode != 0:
        raise RulesetError(
            "GitHub ruleset request failed. Check that gh is authenticated as a repository "
            "administrator with Administration: write permission. No change is claimed."
        )
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RulesetError("GitHub returned an unexpected response; no completion is claimed.") from exc
    if not isinstance(document, dict):
        raise RulesetError("GitHub returned a non-object ruleset response.")
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply the four missing checks using administrator-authenticated gh CLI; default is dry-run",
    )
    args = parser.parse_args(argv)

    try:
        current = _gh_api("GET")
        payload, added = build_updated_payload(current)
        if not added:
            verify_updated_ruleset(current)
            print("PASS: all eight required main-branch CI contexts are already configured.")
            return 0

        print("Target: MSJ1708/shoir-ie main ruleset 26065188")
        print("Missing contexts to add: " + ", ".join(added))
        print("Existing review, strict-check, branch-target and no-bypass settings will be preserved.")
        if not args.apply:
            print("DRY RUN ONLY. Re-run with --apply from an administrator-authenticated gh CLI session.")
            return 0

        updated = _gh_api("PUT", json.dumps(payload))
        verify_updated_ruleset(updated)
        print("PASS: main ruleset updated and re-read response verified with all eight required contexts.")
        return 0
    except RulesetError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
