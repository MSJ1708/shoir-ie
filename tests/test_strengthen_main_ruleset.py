from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "strengthen_main_ruleset.py"
SPEC = importlib.util.spec_from_file_location("strengthen_main_ruleset", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
ruleset_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ruleset_tool)


def sample_ruleset() -> dict:
    return {
        "id": ruleset_tool.RULESET_ID,
        "name": "Protect main — release gates",
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 1,
                    "dismiss_stale_reviews_on_push": True,
                    "required_reviewers": [],
                    "require_code_owner_review": False,
                    "require_last_push_approval": True,
                    "required_review_thread_resolution": True,
                    "require_extra_approval_for_unattributed_changes": True,
                    "allowed_merge_methods": ["merge", "squash", "rebase"],
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "do_not_enforce_on_create": False,
                    "required_status_checks": [
                        {"context": "test", "integration_id": 15368},
                        {"context": "edge-function", "integration_id": 15368},
                        {"context": "engine-regression", "integration_id": 15368},
                        {"context": "security-quality", "integration_id": 15368},
                    ],
                },
            },
        ],
    }


def test_main_ruleset_adds_only_four_missing_contexts_and_preserves_protections():
    original = sample_ruleset()
    payload, added = ruleset_tool.build_updated_payload(original)

    assert added == [
        "clean-postgres-migration-replay",
        "postgres-transaction-contract",
        "production-v9-security-backport",
        "excel-intelligence",
    ]
    checks = next(rule for rule in payload["rules"] if rule["type"] == "required_status_checks")
    assert {item["context"] for item in checks["parameters"]["required_status_checks"]} == set(
        ruleset_tool.REQUIRED_CONTEXTS
    )
    assert all(item.get("integration_id") == 15368 for item in checks["parameters"]["required_status_checks"])
    assert checks["parameters"]["strict_required_status_checks_policy"] is True

    pull = next(rule for rule in payload["rules"] if rule["type"] == "pull_request")
    assert pull["parameters"]["required_approving_review_count"] == 1
    assert pull["parameters"]["require_last_push_approval"] is True
    assert pull["parameters"]["required_review_thread_resolution"] is True
    assert payload["bypass_actors"] == []
    assert payload["conditions"] == original["conditions"]
    assert payload["rules"][0:2] == original["rules"][0:2]


def test_main_ruleset_update_is_idempotent():
    payload, added = ruleset_tool.build_updated_payload(sample_ruleset())
    assert len(added) == 4
    second_payload, second_added = ruleset_tool.build_updated_payload(
        {**payload, "id": ruleset_tool.RULESET_ID}
    )
    assert second_added == []
    assert second_payload == payload
    ruleset_tool.verify_updated_ruleset(second_payload)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: r.update({"enforcement": "disabled"}), "not an active branch"),
        (lambda r: r.update({"bypass_actors": [{"actor_id": 1}]}), "bypass actors"),
        (lambda r: r.update({"conditions": {"ref_name": {"include": ["refs/heads/dev"], "exclude": []}}}), "target the default branch"),
    ],
)
def test_ruleset_refuses_drift_in_protected_metadata(mutate, message):
    ruleset = sample_ruleset()
    mutate(ruleset)
    with pytest.raises(ruleset_tool.RulesetError, match=message):
        ruleset_tool.build_updated_payload(ruleset)


def test_ruleset_refuses_weakened_independent_review_protections():
    ruleset = sample_ruleset()
    pull = next(rule for rule in ruleset["rules"] if rule["type"] == "pull_request")
    pull["parameters"]["require_last_push_approval"] = False
    with pytest.raises(ruleset_tool.RulesetError, match="independent-review protections"):
        ruleset_tool.build_updated_payload(ruleset)


def test_ruleset_refuses_missing_strict_check_or_duplicate_statuses():
    ruleset = sample_ruleset()
    checks = next(rule for rule in ruleset["rules"] if rule["type"] == "required_status_checks")
    checks["parameters"]["strict_required_status_checks_policy"] = False
    with pytest.raises(ruleset_tool.RulesetError, match="Strict required-status-check policy"):
        ruleset_tool.build_updated_payload(ruleset)

    ruleset = sample_ruleset()
    checks = next(rule for rule in ruleset["rules"] if rule["type"] == "required_status_checks")
    checks["parameters"]["required_status_checks"].append({"context": "test", "integration_id": 15368})
    with pytest.raises(ruleset_tool.RulesetError, match="Duplicate required"):
        ruleset_tool.build_updated_payload(ruleset)


def test_post_update_verifier_requires_all_eight_contexts():
    payload, _ = ruleset_tool.build_updated_payload(sample_ruleset())
    ruleset_tool.verify_updated_ruleset({**payload, "id": ruleset_tool.RULESET_ID})

def test_ruleset_refuses_boolean_review_count_even_though_bool_is_an_int_subclass():
    ruleset = sample_ruleset()
    pull = next(rule for rule in ruleset["rules"] if rule["type"] == "pull_request")
    pull["parameters"]["required_approving_review_count"] = True
    with pytest.raises(ruleset_tool.RulesetError, match="independent-review protections"):
        ruleset_tool.build_updated_payload(ruleset)

