"""Dedicated Streamlit Community Cloud entrypoint for Shoir-IE staging.

Deploy this file only from the staging-e2e-20261019 branch. It pins the runtime
environment to staging before executing the shared application entrypoint.
The account store still validates the staging Edge URL and publishable key and
fails closed if staging secrets or a matching backend are missing.
"""
from __future__ import annotations

import os
import runpy
from pathlib import Path

# Intentionally override a conflicting environment variable so this dedicated
# entrypoint cannot silently render as production. The account store validates
# the staging backend configuration independently.
os.environ["SHOIR_ENVIRONMENT"] = "staging"

_APP = Path(__file__).resolve().with_name("app.py")
if not _APP.is_file():
    raise RuntimeError("Shoir-IE staging entrypoint could not find the shared app.py.")

runpy.run_path(str(_APP), run_name="__main__")
