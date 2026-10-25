"""Archive validity and privacy-screening tests for Research Pack T087."""
import base64
import hashlib
import io
import json
import zipfile

import pytest

from shoir_100_tool_reproducibility import build_reproducibility_pack


def build(**overrides):
    args={
        "project_name":"Study A","app_version":"1.2.3","git_commit":"abc123",
        "dataset_fingerprint":"a"*64,"method_name":"OLS","method_version":"1.0",
        "parameters":{"alpha":0.05,"model":"y ~ x","synthetic":True},
        "output_summary":{"r_squared":0.93,"observations":50},
        "random_seed":123,"created_at":"2026-10-24T10:00:00+00:00",
    }
    args.update(overrides)
    return build_reproducibility_pack(**args)


def test_pack_is_real_zip_with_member_checksums_and_no_source_data():
    result=build()
    raw=base64.b64decode(result["archive_base64"])
    assert zipfile.is_zipfile(io.BytesIO(raw))
    assert hashlib.sha256(raw).hexdigest()==result["archive_sha256"]
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert archive.testzip() is None
        names=set(archive.namelist())
        assert names=={"manifest.json","environment.json","parameters.json","outputs.json","method_and_limitations.md","checksums.sha256"}
        checksums=archive.read("checksums.sha256").decode()
        for line in checksums.strip().splitlines():
            digest,name=line.split("  ",1)
            assert hashlib.sha256(archive.read(name)).hexdigest()==digest
        manifest=json.loads(archive.read("manifest.json"))
        assert manifest["dataset_fingerprint_sha256"]=="a"*64
        assert "source dataset cells" in manifest["input_scope"]
        assert "secret" not in archive.read("parameters.json").decode().lower()


def test_pack_rejects_sensitive_keys_raw_tables_bad_hash_and_invalid_seed():
    with pytest.raises(ValueError,match="looks sensitive"):
        build(parameters={"api_key":"do-not-package"})
    with pytest.raises(ValueError,match="scalar"):
        build(output_summary={"table":[[1,2],[3,4]]})
    with pytest.raises(ValueError,match="64-character"):
        build(dataset_fingerprint="not-a-hash")
    with pytest.raises(ValueError,match="non-negative integer"):
        build(random_seed=-1)


def test_pack_rejects_naive_timestamp_and_nonfinite_output():
    with pytest.raises(ValueError,match="include a timezone"):
        build(created_at="2026-10-24T10:00:00")
    with pytest.raises(ValueError,match="non-finite"):
        build(output_summary={"r_squared":float("nan")})
