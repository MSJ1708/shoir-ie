"""Regression tests for high-risk readiness and access foundations."""

import builtins

import pandas as pd
import pytest

from shoir_copilot_orchestrator import stage_copilot_decision


def test_decision_staging_fails_closed_if_enterprise_gate_cannot_import(monkeypatch):
    original_import = builtins.__import__

    def fail_enterprise_layer(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "shoir_enterprise_layer":
            raise ImportError("test-only simulated missing authorization layer")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fail_enterprise_layer)

    with pytest.raises(RuntimeError, match="authorization service could not be loaded"):
        stage_copilot_decision(
            {
                "run_id": "test-run",
                "module": "Engineering Validation Center",
                "result": pd.DataFrame({"value": [1, 2]}),
            },
            actor="disposable-test-user",
        )
