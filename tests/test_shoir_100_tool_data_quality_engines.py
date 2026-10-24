"""Independent fixtures for industrial field mapping and safety incident trends."""
import pandas as pd
import pytest

from shoir_100_tool_data_quality_engines import map_industrial_fields, analyze_safety_incident_trends


def test_field_mapper_suggests_aliases_preserves_original_and_flags_unknowns():
    result = map_industrial_fields(["Asset ID", "kWh", "Produced Units", "custom_field"])
    table = result["mapping_table"].set_index("source_column")
    assert table.loc["Asset ID", "canonical_field"] == "asset_id"
    assert table.loc["Asset ID", "original_column_preserved"] == "Asset ID"
    assert table.loc["kWh", "canonical_field"] == "energy_kwh"
    assert table.loc["Produced Units", "canonical_field"] == "units_produced"
    assert table.loc["custom_field", "mapping_status"] == "UNMAPPED"
    assert result["metrics"]["unmapped_count"] == 1


def test_field_mapper_uses_confirmed_overrides_and_flags_duplicate_targets():
    result = map_industrial_fields(["asset_no", "equipment"], {"asset_no": "asset_id", "equipment": "asset_id"})
    assert result["metrics"]["duplicate_target_count"] == 1
    assert set(result["mapping_table"]["mapping_status"]) == {"DUPLICATE_CANONICAL_TARGET_REVIEW"}
    override = map_industrial_fields(["unexpected"], {"unexpected": "asset_id"})
    assert override["mapping_table"].iloc[0]["mapping_status"] == "MANUALLY_MAPPED"
    with pytest.raises(ValueError, match="unknown canonical target"):
        map_industrial_fields(["source"], {"source": "wrong_target"})


def test_field_mapper_rejects_duplicate_source_columns():
    with pytest.raises(ValueError, match="unique ignoring case"):
        map_industrial_fields(["Asset ID", "asset id"])


def test_safety_rate_uses_exposure_once_per_period_and_reports_categories():
    result = analyze_safety_incident_trends([
        {"period":"P1","incident_category":"Slip","incident_count":2,"exposure_hours":10000},
        {"period":"P1","incident_category":"Pinch","incident_count":1,"exposure_hours":10000},
        {"period":"P2","incident_category":"Slip","incident_count":1,"exposure_hours":20000},
    ])
    assert result["metrics"]["incident_count"] == 4
    assert result["metrics"]["exposure_hours"] == 30000
    assert result["metrics"]["overall_incident_rate"] == pytest.approx(4 / 30000 * 200000)
    assert result["period_summary"].set_index("period").loc["P1","incident_count"] == 3
    assert result["category_summary"].iloc[0]["incident_category"] == "Slip"


def test_safety_trends_reject_duplicate_rows_and_inconsistent_exposure_denominators():
    base={"period":"P1","incident_category":"Slip","incident_count":1,"exposure_hours":100}
    with pytest.raises(ValueError,match="combination must be unique"):
        analyze_safety_incident_trends([base,base])
    with pytest.raises(ValueError,match="identical across category rows"):
        analyze_safety_incident_trends([base,{**base,"incident_category":"Pinch","exposure_hours":200}])


def test_safety_trends_rejects_invalid_counts_and_zero_rate_denominator():
    base={"period":"P1","incident_category":"Slip","incident_count":1,"exposure_hours":100}
    with pytest.raises(ValueError,match="non-negative integer"):
        analyze_safety_incident_trends([{**base,"incident_count":-1}])
    with pytest.raises(ValueError,match="greater than zero"):
        analyze_safety_incident_trends([base],rate_denominator_hours=0)
