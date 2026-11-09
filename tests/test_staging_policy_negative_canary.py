def test_intentional_staging_policy_negative_canary():
    """INTENTIONAL FAILURE: this file must never be merged.

    It tests whether the staging branch blocks a pull request when its only
    currently required status context (test) fails.
    """
    assert False, "INTENTIONAL STAGING POLICY CANARY FAILURE — DO NOT MERGE"
