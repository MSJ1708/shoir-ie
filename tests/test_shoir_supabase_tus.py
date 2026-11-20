from __future__ import annotations

import base64

import pytest
import requests

import shoir_supabase_tus as tus


class FakeResponse:
    def __init__(self, status_code=200, headers=None):
        self.status_code = status_code
        self.headers = dict(headers or {})


class FakeTusSession:
    def __init__(self, length, *, location="/storage/v1/upload/resumable/test-upload", start_offset=0):
        self.length = length
        self.location = location
        self.offset = start_offset
        self.calls = []
        self.first_patch_lost_after_accept = False
        self.first_patch_lost_before_accept = False
        self.bad_patch_offset = False
        self.post_response = FakeResponse(201, {"Location": location})

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.post_response

    def head(self, url, **kwargs):
        self.calls.append(("HEAD", url, kwargs))
        return FakeResponse(
            200,
            {"Upload-Length": str(self.length), "Upload-Offset": str(self.offset)},
        )

    def patch(self, url, **kwargs):
        self.calls.append(("PATCH", url, kwargs))
        if self.first_patch_lost_after_accept:
            self.first_patch_lost_after_accept = False
            self.offset += len(kwargs["data"])
            raise requests.ConnectionError("simulated lost response")
        if self.first_patch_lost_before_accept:
            self.first_patch_lost_before_accept = False
            raise requests.ConnectionError("simulated lost request")
        if self.bad_patch_offset:
            return FakeResponse(204, {"Upload-Offset": str(self.offset + len(kwargs["data"]) + 1)})
        supplied_offset = int(kwargs["headers"]["Upload-Offset"])
        if supplied_offset != self.offset:
            return FakeResponse(409, {})
        self.offset += len(kwargs["data"])
        return FakeResponse(204, {"Upload-Offset": str(self.offset)})

    def close(self):
        return None


def test_tus_signed_upload_uses_safe_metadata_and_six_mib_chunks(monkeypatch):
    monkeypatch.setattr(tus.time, "sleep", lambda _: None)
    content = b"x" * (tus.TUS_CHUNK_BYTES + 19)
    session = FakeTusSession(len(content))
    remembered = []

    result = tus.upload_signed_tus(
        project_ref="hfhrosthswcybccepmak",
        bucket_name="shoir-industrial-datasets",
        object_name="tmp/" + "a" * 32 + "/DS-" + "A" * 12 + "/upload.csv",
        content_type="text/csv",
        signed_upload_token="signed-upload-token-123456",
        file_bytes=content,
        on_upload_url=remembered.append,
        http_session=session,
    )

    assert result == "https://hfhrosthswcybccepmak.storage.supabase.co" + session.location
    assert remembered == [result]
    post = next(call for call in session.calls if call[0] == "POST")
    headers = post[2]["headers"]
    assert headers["Tus-Resumable"] == "1.0.0"
    assert headers["Upload-Length"] == str(len(content))
    assert headers["x-signature"] == "signed-upload-token-123456"
    assert headers["x-upsert"] == "false"
    encoded = dict(item.split(" ", 1) for item in headers["Upload-Metadata"].split(","))
    assert base64.b64decode(encoded["bucketName"]).decode() == "shoir-industrial-datasets"
    assert base64.b64decode(encoded["objectName"]).decode().endswith("/upload.csv")
    patches = [call for call in session.calls if call[0] == "PATCH"]
    assert [len(call[2]["data"]) for call in patches] == [tus.TUS_CHUNK_BYTES, 19]
    assert all(call[2]["allow_redirects"] is False for call in session.calls)


def test_tus_recovers_when_patch_response_is_lost_after_remote_acceptance(monkeypatch):
    monkeypatch.setattr(tus.time, "sleep", lambda _: None)
    content = b"recover-me" * 100
    session = FakeTusSession(len(content))
    session.first_patch_lost_after_accept = True

    tus.upload_signed_tus(
        project_ref="hfhrosthswcybccepmak",
        bucket_name="shoir-industrial-datasets",
        object_name="tmp/" + "b" * 32 + "/DS-" + "B" * 12 + "/upload.csv",
        content_type="text/csv",
        signed_upload_token="signed-upload-token-123456",
        file_bytes=content,
        http_session=session,
    )

    patches = [call for call in session.calls if call[0] == "PATCH"]
    assert len(patches) == 1
    assert session.offset == len(content)
    assert any(call[0] == "HEAD" for call in session.calls)


def test_tus_retries_when_patch_was_not_accepted(monkeypatch):
    monkeypatch.setattr(tus.time, "sleep", lambda _: None)
    content = b"retry-me"
    session = FakeTusSession(len(content))
    session.first_patch_lost_before_accept = True

    tus.upload_signed_tus(
        project_ref="hfhrosthswcybccepmak",
        bucket_name="shoir-industrial-datasets",
        object_name="tmp/" + "c" * 32 + "/DS-" + "C" * 12 + "/upload.csv",
        content_type="text/csv",
        signed_upload_token="signed-upload-token-123456",
        file_bytes=content,
        http_session=session,
    )

    patches = [call for call in session.calls if call[0] == "PATCH"]
    assert len(patches) == 2
    assert session.offset == len(content)


def test_tus_can_resume_existing_upload_at_server_confirmed_offset(monkeypatch):
    monkeypatch.setattr(tus.time, "sleep", lambda _: None)
    content = b"abcdef"
    session = FakeTusSession(len(content), start_offset=3)

    tus.upload_signed_tus(
        project_ref="hfhrosthswcybccepmak",
        bucket_name="shoir-industrial-datasets",
        object_name="tmp/" + "d" * 32 + "/DS-" + "D" * 12 + "/upload.csv",
        content_type="text/csv",
        signed_upload_token="",
        file_bytes=content,
        resume_url="https://hfhrosthswcybccepmak.storage.supabase.co/storage/v1/upload/resumable/test-upload",
        http_session=session,
    )

    assert not any(call[0] == "POST" for call in session.calls)
    patch = next(call for call in session.calls if call[0] == "PATCH")
    assert patch[2]["headers"]["Upload-Offset"] == "3"
    assert patch[2]["data"] == b"def"


def test_tus_rejects_untrusted_location_and_never_follows_redirects(monkeypatch):
    monkeypatch.setattr(tus.time, "sleep", lambda _: None)
    session = FakeTusSession(4)
    session.post_response = FakeResponse(
        201,
        {"Location": "https://attacker.example/storage/v1/upload/resumable/leak"},
    )

    with pytest.raises(RuntimeError, match="untrusted"):
        tus.upload_signed_tus(
            project_ref="hfhrosthswcybccepmak",
            bucket_name="shoir-industrial-datasets",
            object_name="tmp/" + "e" * 32 + "/DS-" + "E" * 12 + "/upload.csv",
            content_type="text/csv",
            signed_upload_token="signed-upload-token-123456",
            file_bytes=b"data",
            http_session=session,
        )
    assert session.calls[0][2]["allow_redirects"] is False


def test_tus_rejects_inconsistent_server_offsets(monkeypatch):
    monkeypatch.setattr(tus.time, "sleep", lambda _: None)
    session = FakeTusSession(4)
    session.bad_patch_offset = True

    with pytest.raises(RuntimeError, match="offset changed"):
        tus.upload_signed_tus(
            project_ref="hfhrosthswcybccepmak",
            bucket_name="shoir-industrial-datasets",
            object_name="tmp/" + "f" * 32 + "/DS-" + "F" * 12 + "/upload.csv",
            content_type="text/csv",
            signed_upload_token="signed-upload-token-123456",
            file_bytes=b"data",
            http_session=session,
        )
