from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from authenticated_release_gate import preflight_candidate_organization_actions


class FakeEdgeAPI:
    def __init__(self, supported_actions):
        self.supported_actions = set(supported_actions)
        self.calls = []

    def call(self, action, payload):
        self.calls.append((action, payload))
        if action in self.supported_actions:
            return 401, {"error": "Unauthorized session."}
        return 400, {"error": "Unsupported action."}


REQUIRED_ACTIONS = {
    "org_member_suspend_session",
    "org_member_restore_session",
    "org_close_session",
}


def test_candidate_organization_preflight_accepts_all_handlers_without_session():
    api = FakeEdgeAPI(REQUIRED_ACTIONS)

    ready, detail = preflight_candidate_organization_actions(api, "shoir-e2e-active")

    assert ready is True
    assert "exposed" in detail
    assert {action for action, _ in api.calls} == REQUIRED_ACTIONS
    assert all(payload["token"].startswith("shoir-e2e-invalid-") for _, payload in api.calls)


def test_candidate_organization_preflight_blocks_before_any_write_when_handler_missing():
    api = FakeEdgeAPI(REQUIRED_ACTIONS - {"org_close_session"})

    ready, detail = preflight_candidate_organization_actions(api, "shoir-e2e-active")

    assert ready is False
    assert "org_close_session" in detail
    assert len(api.calls) == 3
    assert all(payload["token"].startswith("shoir-e2e-invalid-") for _, payload in api.calls)


def test_candidate_organization_preflight_fails_closed_on_unexpected_status():
    class UnexpectedAPI:
        def __init__(self):
            self.calls = []

        def call(self, action, payload):
            self.calls.append(action)
            return 200, {"ok": True}

    api = UnexpectedAPI()
    ready, detail = preflight_candidate_organization_actions(api, "shoir-e2e-active")

    assert ready is False
    assert "expected invalid-session guard" in detail
    assert api.calls == ["org_member_suspend_session"]
