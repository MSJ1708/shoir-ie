def test_intentional_policy_negative_canary():
    """INTENTIONAL FAILURE: this file must never be merged.

    It exists only to prove that the protected main branch rejects a PR
    when its required GitHub Actions test check fails.
    """
    assert False, "INTENTIONAL POLICY CANARY FAILURE — DO NOT MERGE"
