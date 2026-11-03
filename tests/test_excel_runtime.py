import io

import pandas as pd

from shoir_excel_runtime import process_fast


def test_ooxml_preflight_rejects_traversal_and_resource_exhaustion(monkeypatch):
    import zipfile

    import pytest

    import shoir_excel_runtime as runtime

    traversal = io.BytesIO()
    with zipfile.ZipFile(traversal, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("../outside.xml", b"not allowed")
    with pytest.raises(ValueError, match="unsafe package path"):
        runtime._validate_ooxml_package(traversal.getvalue(), "unsafe.xlsx")

    windows_path = io.BytesIO()
    with zipfile.ZipFile(windows_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("C:/outside.xml", b"not allowed")
    with pytest.raises(ValueError, match="unsafe package path"):
        runtime._validate_ooxml_package(windows_path.getvalue(), "windows-path.xlsx")

    symlink = io.BytesIO()
    link_info = zipfile.ZipInfo("xl/linked.xml")
    link_info.create_system = 3
    link_info.external_attr = (0o120777 << 16)
    with zipfile.ZipFile(symlink, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr(link_info, "../outside.xml")
    with pytest.raises(ValueError, match="Symbolic links"):
        runtime._validate_ooxml_package(symlink.getvalue(), "symlink.xlsx")

    compressed = io.BytesIO()
    with zipfile.ZipFile(compressed, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("xl/workbook.xml", b"A" * 4096)

    monkeypatch.setattr(runtime, "MAX_OOXML_COMPRESSION_RATIO", 5)
    with pytest.raises(ValueError, match="unusually compressed"):
        runtime._validate_ooxml_package(compressed.getvalue(), "compressed.xlsx")

    monkeypatch.setattr(runtime, "MAX_OOXML_COMPRESSION_RATIO", 100_000)
    monkeypatch.setattr(runtime, "MAX_OOXML_UNCOMPRESSED_BYTES", 128)
    with pytest.raises(ValueError, match="expands beyond"):
        runtime._validate_ooxml_package(compressed.getvalue(), "oversized.xlsx")


def test_process_fast_loads_workbook_without_building_exports():
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        pd.DataFrame(
            [
                ["Operations export", None],
                ["SKU", "Demand"],
                [" A-01 ", "1,200"],
                ["A-02", "950"],
            ]
        ).to_excel(writer, index=False, header=False, sheet_name="Orders")

    result = process_fast(buf.getvalue(), "orders.xlsx")

    assert list(result["cleaned_sheets"]) == ["Orders"]
    frame = result["cleaned_sheets"]["Orders"]
    assert frame["SKU"].tolist() == ["A-01", "A-02"]
    assert frame["Demand"].tolist() == [1200, 950]
    assert result["xlsx"] is None
    assert result["bundle"] is None
    assert result["signature"]


def test_ooxml_fidelity_scan_flags_formula_chart_named_range_and_validation_risks():
    from shoir_excel_foundation import fast_workbook_fidelity_report

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        pd.DataFrame({"Quantity": [2], "Unit Price": [5.0]}).to_excel(
            writer, index=False, sheet_name="Data"
        )
        worksheet = writer.sheets["Data"]
        worksheet.write_formula("C2", "=A2*B2")
        worksheet.data_validation("A2:A20", {"validate": "integer", "criteria": ">", "value": 0})
        chart = writer.book.add_chart({"type": "column"})
        chart.add_series({"values": "=Data!$B$2:$B$2"})
        worksheet.insert_chart("E2", chart)
        writer.book.define_name("QuantityInput", "=Data!$A$2")

    report = fast_workbook_fidelity_report(buf.getvalue(), "source-with-features.xlsx")

    assert report["Formula cells"] == 1
    assert report["Charts present"] is True
    assert report["Named ranges present"] is True
    assert report["Data validations present"] is True
    assert report["Requires acknowledgement"] is True
    assert any("Source formulas" in item for item in report["Unsupported features"])
    assert "original upload remains unchanged" in report["Fidelity warning"]


def test_ooxml_fidelity_scan_detects_tables_filters_merges_and_hidden_bands():
    from shoir_excel_foundation import fast_workbook_fidelity_report

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        pd.DataFrame(
            {"Line": ["A", "B"], "Output": [10, 12], "Cost": [5.0, 6.0]}
        ).to_excel(writer, index=False, sheet_name="Data")
        worksheet = writer.sheets["Data"]
        table_sheet = writer.book.add_worksheet("TableSource")
        table_sheet.write_row(0, 0, ["ID", "Measure"])
        table_sheet.write_row(1, 0, ["A", 10])
        table_sheet.write_row(2, 0, ["B", 12])
        table_sheet.add_table(
            0, 0, 2, 1,
            {"name": "ProductionTable", "columns": [
                {"header": "ID"}, {"header": "Measure"}
            ]},
        )
        worksheet.autofilter(0, 0, 2, 2)
        worksheet.merge_range("E1:F1", "Merged title")
        styled_header = writer.book.add_format({"bold": True, "bg_color": "#163A5F"})
        worksheet.write("A1", "Line", styled_header)
        worksheet.set_row(1, None, styled_header, {"hidden": True})
        worksheet.set_column("C:C", None, styled_header, {"hidden": True})

    report = fast_workbook_fidelity_report(buf.getvalue(), "fidelity-matrix.xlsx")

    assert report["Cell formatting present"] is True
    assert report["Tables present"] is True
    assert report["Auto filters present"] is True
    assert report["Merged cells present"] is True
    assert report["Hidden rows present"] is True
    assert report["Hidden columns present"] is True
    assert report["Requires acknowledgement"] is True
    for feature in ("Source Excel tables", "filters", "Merged cells", "Hidden rows", "Hidden columns"):
        assert any(feature in item for item in report["Unsupported features"])


def test_source_formula_scan_is_bounded_and_exports_formulas_as_inert_evidence(monkeypatch):
    import pytest
    from openpyxl import load_workbook

    import shoir_excel_runtime as runtime

    source_buffer = io.BytesIO()
    with pd.ExcelWriter(source_buffer, engine="xlsxwriter") as writer:
        pd.DataFrame(
            {"Item": ["A"], "Quantity": [2], "Unit Price": [5], "Total": [None]}
        ).to_excel(writer, index=False, sheet_name="Data")
        writer.sheets["Data"].write_formula("D2", "=B2*C2")

    raw = source_buffer.getvalue()
    result = process_fast(raw, "formula-source.xlsx")
    assert result["formula_scan_status"] == "NOT_SCANNED"
    assert result["formula_inventory"] == []

    scan = runtime.scan_source_formulas(result, raw)
    assert scan["status"] == "COMPLETE"
    assert scan["formula_count"] == 1
    assert result["formula_inventory"][0]["Sheet"] == "Data"
    assert result["formula_inventory"][0]["Cell"] == "D2"
    assert result["formula_inventory"][0]["Formula"] == "=B2*C2"

    with pytest.raises(ValueError, match="changed"):
        runtime.scan_source_formulas(result, raw + b"tampered")

    # The bounded scanner refuses very large worksheet dimensions rather than
    # iterating through unbounded cell ranges.
    monkeypatch.setattr(runtime, "MAX_FORMULA_SCAN_CELLS", 1)
    with pytest.raises(ValueError, match="formula-inspection limit"):
        runtime.scan_source_formulas(result, raw)

    monkeypatch.setattr(runtime, "MAX_FORMULA_SCAN_CELLS", 2_000_000)
    scan = runtime.scan_source_formulas(result, raw)
    runtime.prepare_exports(result, acknowledged_fidelity_risk=True)

    workbook = load_workbook(io.BytesIO(result["xlsx"]), data_only=False, read_only=False)
    assert "FORMULA INVENTORY" in workbook.sheetnames
    cell = workbook["FORMULA INVENTORY"]["C5"]
    assert cell.value == "=B2*C2"
    assert cell.data_type != "f", "Source formula evidence must be inert text, not an executable formula."
    workbook.close()


def test_prepare_exports_requires_acknowledgement_for_unsupported_source_features():
    import pytest

    from shoir_excel_runtime import prepare_exports

    clean = pd.DataFrame({"Value": [1, 2]})
    result = {
        "cleaned_sheets": {"Data": clean},
        "raw_sheets": {"Data": clean.copy(deep=True)},
        "audits": {"Data": []},
        "profiles": {"Data": {"Readiness": "READY", "Quality score": 100.0, "Schema fingerprint": "TEST"}},
        "fidelity_report": {
            "Requires acknowledgement": True,
            "Unsupported features": ["Source formulas"],
        },
    }
    with pytest.raises(PermissionError, match="acknowledge"):
        prepare_exports(result)

    # Explicit acknowledgement permits creation of a separate data-focused copy.
    prepare_exports(result, acknowledged_fidelity_risk=True)
    assert isinstance(result["xlsx"], bytes) and result["xlsx"]


def test_multi_sheet_export_is_a_valid_separate_workbook_with_raw_archives():
    import hashlib
    import json
    import zipfile

    from openpyxl import load_workbook
    from shoir_excel_runtime import prepare_exports

    source_buffer = io.BytesIO()
    with pd.ExcelWriter(source_buffer, engine="xlsxwriter") as writer:
        pd.DataFrame(
            [["Production export", None], ["Line", "Output"], ["A", 100], ["B", 120]]
        ).to_excel(writer, index=False, header=False, sheet_name="Production")
        pd.DataFrame(
            [["Downtime report", None], ["Line", "Minutes"], ["A", 15], ["B", 8]]
        ).to_excel(writer, index=False, header=False, sheet_name="Downtime")

    original_bytes = source_buffer.getvalue()
    original_hash = hashlib.sha256(original_bytes).hexdigest()
    result = process_fast(original_bytes, "plant-data.xlsx")

    assert list(result["cleaned_sheets"]) == ["Production", "Downtime"]
    assert result["cleaned_sheets"]["Production"]["Output"].tolist() == [100, 120]
    assert result["cleaned_sheets"]["Downtime"]["Minutes"].tolist() == [15, 8]
    assert result["xlsx"] is None
    assert result["bundle"] is None

    prepare_exports(result)

    # Export creates a separate artifact; the uploaded source bytes are immutable.
    assert hashlib.sha256(original_bytes).hexdigest() == original_hash
    assert isinstance(result["xlsx"], bytes) and result["xlsx"]
    assert isinstance(result["bundle"], bytes) and result["bundle"]

    workbook = load_workbook(io.BytesIO(result["xlsx"]), data_only=False, read_only=False)
    assert "START HERE" in workbook.sheetnames
    assert "EXECUTIVE DASHBOARD" in workbook.sheetnames
    assert "SOURCE METADATA" in workbook.sheetnames
    assert "CLEAN - Production" in workbook.sheetnames
    assert "CLEAN - Downtime" in workbook.sheetnames
    assert workbook["RAW - Production"].sheet_state == "hidden"
    assert workbook["RAW - Downtime"].sheet_state == "hidden"
    assert workbook["CLEAN - Production"]["A7"].value == "A"
    assert workbook["CLEAN - Production"]["B7"].value == 100
    workbook.close()

    with zipfile.ZipFile(io.BytesIO(result["xlsx"])) as xlsx_archive:
        assert xlsx_archive.testzip() is None
    with zipfile.ZipFile(io.BytesIO(result["bundle"])) as evidence_archive:
        assert evidence_archive.testzip() is None
        names = set(evidence_archive.namelist())
        assert "shoir_ie_industrial_excel_workbook.xlsx" in names
        assert "manifest.json" in names
        assert "raw_csv/Production.csv" in names
        assert "clean_csv/Production.csv" in names
        manifest = json.loads(evidence_archive.read("manifest.json"))
        assert manifest["source_sheets"] == ["Production", "Downtime"]
        assert manifest["cleaned_sheets"] == ["Production", "Downtime"]


def test_process_fast_rejects_unsupported_large_upload_before_parsing():
    raw = b"x" * (75 * 1024 * 1024 + 1)
    try:
        process_fast(raw, "too_large.xlsx")
    except ValueError as exc:
        assert "limited to 75 mb" in str(exc).lower()
    else:
        raise AssertionError("Large uploads must be rejected before workbook parsing.")

def test_premium_excel_module_fails_closed_before_upload_without_live_entitlement(monkeypatch):
    import streamlit as st
    import durable_account_store as account_store

    from shoir_excel_runtime import render_excel_intelligence_safe

    monkeypatch.setattr(
        st,
        "session_state",
        {
            "authenticated": True,
            "current_user": "synthetic-enterprise-user",
            "user_tier": "Enterprise Tier",
        },
    )
    monkeypatch.setattr(account_store, "edge_backend_configured", lambda: False)
    warnings = []
    monkeypatch.setattr(st, "warning", lambda message: warnings.append(str(message)))
    monkeypatch.setattr(
        st,
        "file_uploader",
        lambda *args, **kwargs: pytest.fail("Premium upload UI must not render without live entitlement."),
    )

    render_excel_intelligence_safe(
        "Enterprise Tier",
        "synthetic-enterprise-user",
        enable_copilot=True,
    )

    assert len(warnings) == 1
    assert "session and subscription could not be verified" in warnings[0]


def test_excel_intelligence_copilot_requires_approval_and_keeps_source_read_only(monkeypatch):
    import json
    import zipfile

    import pytest
    import streamlit as st

    from shoir_excel_runtime import (
        build_excel_intelligence_plan,
        execute_excel_intelligence_plan,
    )

    source = pd.DataFrame(
        {
            "Line": ["A", "B", "C"],
            "Throughput": [100, 120, 115],
            "Operating Cost": [50.0, 55.0, 53.0],
        }
    )
    original = source.copy(deep=True)
    prompt = "Summarise throughput and operating cost"

    monkeypatch.delenv("SHOIR_EXCEL_INTELLIGENCE_MINIMUM_TIER", raising=False)
    monkeypatch.setattr(
        st,
        "session_state",
        {
            "authenticated": True,
            "current_user": "shoir-e2e-excel-copilot",
            "workspace_id": "test-workspace",
            "user_tier": "Enterprise Tier",
            "subscription_expires_at": "2099-01-01T00:00:00Z",
            "remote_session_token": "synthetic-live-session-token",
        },
    )

    import durable_account_store as account_store
    live_account = {
        "ok": True,
        "username": "shoir-e2e-excel-copilot",
        "tier": "Enterprise Tier",
        "active": True,
        "expires_at": "2099-01-01T00:00:00Z",
    }
    monkeypatch.setattr(account_store, "edge_backend_configured", lambda: True)

    def mock_live_entitlement(username, token):
        assert username == "shoir-e2e-excel-copilot"
        assert token == "synthetic-live-session-token"
        return dict(live_account)

    monkeypatch.setattr(account_store, "edge_session_entitlement", mock_live_entitlement)

    plan = build_excel_intelligence_plan(prompt, "Production", source)
    assert plan["plan"]["requires_approval"] is True
    assert plan["external_model_used"] is False
    assert len(plan["request_fingerprint"]) == 64
    assert len(plan["plan_id"]) == 32
    assert plan["plan_id"].isalnum()
    assert plan["owner_username"] == "shoir-e2e-excel-copilot"
    assert plan["workspace_id"] == "test-workspace"

    with pytest.raises(PermissionError, match="Explicit approval"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=False,
        )

    with pytest.raises(PermissionError, match="subscription"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Starter", approved=True,
        )

    # A caller cannot claim Enterprise when the authenticated session is Starter.
    st.session_state["user_tier"] = "Starter Tier"
    with pytest.raises(PermissionError, match="subscription"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=True,
        )
    st.session_state["user_tier"] = "Enterprise Tier"

    # Expired, missing and malformed live account expiry values fail closed.
    live_account["expires_at"] = "2000-01-01T00:00:00Z"
    with pytest.raises(PermissionError, match="expired"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=True,
        )
    live_account["expires_at"] = None
    with pytest.raises(PermissionError, match="expiry"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=True,
        )
    live_account["expires_at"] = "not-a-date"
    with pytest.raises(PermissionError, match="expiry"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=True,
        )
    live_account["expires_at"] = "2099-01-01T00:00:00Z"

    # Live entitlement, not a client-supplied tier, controls execution.
    live_account["tier"] = "Starter Tier"
    with pytest.raises(PermissionError, match="subscription"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=True,
        )
    live_account["tier"] = "Enterprise Tier"

    live_account["active"] = False
    with pytest.raises(PermissionError, match="inactive"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=True,
        )
    live_account["active"] = True

    live_account["username"] = "another-user"
    with pytest.raises(PermissionError, match="does not match"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=True,
        )
    live_account["username"] = "shoir-e2e-excel-copilot"

    monkeypatch.setattr(account_store, "edge_backend_configured", lambda: False)
    with pytest.raises(PermissionError, match="unavailable"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=True,
        )
    monkeypatch.setattr(account_store, "edge_backend_configured", lambda: True)

    def invalid_backend_configuration():
        raise RuntimeError("synthetic invalid staging configuration")

    monkeypatch.setattr(account_store, "edge_backend_configured", invalid_backend_configuration)
    with pytest.raises(PermissionError, match="unavailable"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=True,
        )
    monkeypatch.setattr(account_store, "edge_backend_configured", lambda: True)

    with pytest.raises(ValueError, match="stale"):
        execute_excel_intelligence_plan(
            prompt + " with a different instruction",
            "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=True,
        )

    tampered = dict(plan)
    tampered["plan"] = {**plan["plan"], "steps": [{"step": "unapproved operation"}]}
    with pytest.raises(ValueError, match="plan changed"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, tampered,
            "shoir-e2e-excel-copilot", "Enterprise", approved=True,
        )

    # A valid plan from another actor or workspace must not be reusable,
    # even when that other actor is also authenticated and entitled.
    st.session_state["current_user"] = "another-e2e-user"
    with pytest.raises(PermissionError, match="another user or workspace"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "another-e2e-user", "Enterprise", approved=True,
        )
    st.session_state["current_user"] = "shoir-e2e-excel-copilot"

    st.session_state["workspace_id"] = "another-workspace"
    with pytest.raises(PermissionError, match="another user or workspace"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=True,
        )
    st.session_state["workspace_id"] = "test-workspace"

    run = execute_excel_intelligence_plan(
        prompt, "Production", source, plan,
        "shoir-e2e-excel-copilot", "Enterprise", approved=True,
    )

    pd.testing.assert_frame_equal(source, original)
    assert run["planner"] == "Shoir-IE deterministic Copilot orchestrator"
    assert run["external_model_used"] is False
    assert run["source_sheet"] == "Production"
    assert run["evidence_manifest"]["approval_required"] is True
    assert run["approval_record"]["approved"] is True
    assert run["approval_record"]["plan_id"] == plan["plan_id"]
    assert run["approval_record"]["source_data_preserved"] is True
    assert run["approval_record"]["execution_status"] == "COMPLETED"
    with zipfile.ZipFile(io.BytesIO(run["export"]), "r") as archive:
        assert "copilot_analysis.xlsx" in archive.namelist()
        assert "inspection.json" in archive.namelist()
        assert "evidence_manifest.json" in archive.namelist()
        assert "copilot_approval.json" in archive.namelist()
        approval = json.loads(archive.read("copilot_approval.json"))
        assert approval["plan_id"] == plan["plan_id"]
        assert approval["approved"] is True
        assert approval["source_worksheet"] == "Production"

    # A repeated click/replay of the exact same plan must be rejected, even
    # though its request, data and approval checkbox value have not changed.
    with pytest.raises(PermissionError, match="already run"):
        execute_excel_intelligence_plan(
            prompt, "Production", source, plan,
            "shoir-e2e-excel-copilot", "Enterprise", approved=True,
        )

    # Rebuilding the same request creates a different plan ID, so a genuinely
    # new review/approval is possible without carrying the old approval forward.
    rebuilt_plan = build_excel_intelligence_plan(prompt, "Production", source)
    assert rebuilt_plan["request_fingerprint"] == plan["request_fingerprint"]
    assert rebuilt_plan["plan_id"] != plan["plan_id"]


def test_excel_evidence_csv_neutralizes_formula_like_text_and_preserves_source_frames():
    import csv
    import zipfile

    from shoir_excel_studio import build_ultimate_bundle

    source = pd.DataFrame({
        "=UntrustedHeader": [
            '  =HYPERLINK("https://invalid.example","open")',
            "\t+1+1",
            "-1+2",
            "@SUM(A1:A2)",
            "ordinary text",
        ]
    })
    original = source.copy(deep=True)
    bundle = build_ultimate_bundle(
        "Synthetic formula injection test",
        b"synthetic-xlsx-bytes",
        audits={"Sheet1": []},
        profiles={"Sheet1": {}},
        cleaned_sheets={"Sheet1": source},
        raw_sheets={"Sheet1": source},
        field_intelligence=[{"Field": "=1+2"}],
        review_register=[{"Finding": "\t=CMD()"}],
        source_metadata=[{"Source": "+HYPERLINK()"}],
    )

    with zipfile.ZipFile(io.BytesIO(bundle), "r") as archive:
        names = set(archive.namelist())
        assert "clean_csv/Sheet1.csv" in names
        assert "raw_csv/Sheet1.csv" in names
        for name in (
            "clean_csv/Sheet1.csv",
            "raw_csv/Sheet1.csv",
            "field_intelligence.csv",
            "validation_review.csv",
            "source_metadata.csv",
        ):
            rows = list(csv.reader(io.StringIO(archive.read(name).decode("utf-8"))))
            for row in rows:
                for value in row:
                    candidate = value.lstrip(" \t\r\n\x00\x0b\x0c")
                    assert not candidate.startswith(("=", "+", "-", "@"))

    pd.testing.assert_frame_equal(source, original)


def test_upload_failure_hides_exception_details_and_logs_server_side(caplog):
    from shoir_excel_runtime import _record_upload_failure

    private_error = ValueError(
        "private path=/srv/shoir/secrets.xlsx token=synthetic-secret-value"
    )
    state = {"excel_studio_safe_result": {"old": "data"}}

    message = _record_upload_failure(state, "synthetic-workbook-signature", private_error)

    assert "EXCEL-" in message
    assert "private path" not in message
    assert "/srv/shoir/secrets.xlsx" not in message
    assert "synthetic-secret-value" not in message
    assert state["excel_studio_safe_result"] is None
    assert "synthetic-secret-value" not in state["excel_studio_safe_error"]
    assert "synthetic-secret-value" in caplog.text
    assert "workbook upload and inspection" in caplog.text


def test_bounded_excel_preview_limits_render_size_without_mutating_source():
    from shoir_excel_runtime import bounded_excel_preview

    source = pd.DataFrame(
        {f"Column {column}": range(2505) for column in range(75)}
    )
    original_shape = source.shape
    preview = bounded_excel_preview(source)

    assert preview.shape == (2000, 50)
    assert source.shape == original_shape
    assert preview.iloc[0, 0] == 0
    assert preview.iloc[-1, -1] == 1999


def test_excel_table_renderer_falls_back_when_streamlit_dataframe_rendering_fails(monkeypatch):
    import shoir_excel_runtime as runtime

    warnings = []
    text_previews = []
    captions = []

    def fail_dataframe(*args, **kwargs):
        raise RuntimeError("simulated Streamlit frontend serialization issue")

    monkeypatch.setattr(runtime.st, "dataframe", fail_dataframe)
    monkeypatch.setattr(runtime.st, "warning", warnings.append)
    monkeypatch.setattr(runtime.st, "text", text_previews.append)
    monkeypatch.setattr(runtime.st, "caption", captions.append)

    frame = pd.DataFrame({"Line": ["A", "B"], "Output": [10, 20]})
    runtime._render_excel_dataframe(frame, "Quality review")

    assert warnings and "text preview instead" in warnings[0]
    assert text_previews and "A" in text_previews[0]


def test_excel_display_frame_sanitizes_mixed_objects_and_duplicate_headers_without_mutating_source():
    from shoir_excel_runtime import _safe_excel_display_frame

    source = pd.DataFrame(
        [[1, "alpha"], ["two", {"nested": [1, 2]}], [None, b"binary"], ["long", "z" * 2100]],
        columns=["Mixed", "Mixed"],
    )
    original = source.copy(deep=True)
    display = _safe_excel_display_frame(source)

    assert list(display.columns) == ["Mixed", "Mixed (2)"]
    assert str(display.dtypes.iloc[0]) == "string"
    assert str(display.dtypes.iloc[1]) == "string"
    assert display.iloc[0, 0] == "1"
    assert display.iloc[1, 0] == "two"
    assert display.iloc[1, 1] == '{"nested": [1, 2]}'
    assert pd.isna(display.iloc[2, 0])
    assert display.iloc[2, 1] == "binary"
    assert len(display.iloc[3, 1]) == 2000
    assert display.iloc[3, 1].endswith("…")
    pd.testing.assert_frame_equal(source, original)


def test_excel_json_renderer_falls_back_when_interactive_json_display_fails(monkeypatch):
    import shoir_excel_runtime as runtime

    warnings = []
    code_blocks = []

    def fail_json(*args, **kwargs):
        raise RuntimeError("simulated JSON tree rendering issue")

    monkeypatch.setattr(runtime.st, "json", fail_json)
    monkeypatch.setattr(runtime.st, "warning", warnings.append)
    monkeypatch.setattr(runtime.st, "code", lambda value, **kwargs: code_blocks.append(value))

    runtime._render_excel_json({"source": "synthetic", "rows": 12}, "Evidence manifest")

    assert warnings and "displayed interactively" in warnings[0]
    assert "simulated JSON tree rendering issue" not in warnings[0]
    assert code_blocks and '"rows": 12' in code_blocks[0]


def test_excel_json_renderer_bounds_large_evidence_previews(monkeypatch):
    import shoir_excel_runtime as runtime

    code_blocks = []
    captions = []
    monkeypatch.setattr(runtime.st, "code", lambda value, **kwargs: code_blocks.append(value))
    monkeypatch.setattr(runtime.st, "caption", captions.append)

    runtime._render_excel_json({"evidence": "x" * 300_000}, "Evidence manifest")

    assert len(code_blocks[0]) <= runtime.MAX_RENDER_JSON_CHARS
    assert captions and "complete evidence remains" in captions[0]


def test_excel_plotly_renderer_skips_oversized_charts(monkeypatch):
    from types import SimpleNamespace

    import shoir_excel_runtime as runtime

    warnings = []
    rendered = []
    monkeypatch.setattr(runtime.st, "warning", warnings.append)
    monkeypatch.setattr(runtime.st, "plotly_chart", lambda *args, **kwargs: rendered.append(args[0]))

    oversized = SimpleNamespace(
        data=[SimpleNamespace(x=list(range(runtime.MAX_RENDER_CHART_POINTS + 1)),
                              y=list(range(runtime.MAX_RENDER_CHART_POINTS + 1)))]
    )
    runtime._render_excel_plotly_figure(oversized, "Copilot chart")

    assert not rendered
    assert warnings and "above the" in warnings[0]
    assert "full result table" in warnings[0]


def test_excel_plotly_renderer_falls_back_when_plotly_rendering_raises(monkeypatch):
    import shoir_excel_runtime as runtime

    warnings = []
    monkeypatch.setattr(runtime.st, "warning", warnings.append)
    monkeypatch.setattr(
        runtime.st,
        "plotly_chart",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("frontend chart serialization")),
    )
    figure = type("Figure", (), {"data": []})()

    runtime._render_excel_plotly_figure(figure, "Copilot chart")

    assert warnings and "underlying analysis table" in warnings[0]
