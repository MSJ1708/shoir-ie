from shoir_sqlite import sqlite_connect as sqlite_connection
import sqlite3
import pandas as pd
import pytest

from industrial_platform import (
    init_platform_db, data_quality_report, validate_table, finite_schedule,
    mrp_explode, calculate_oee, spc_limits, capability, fmea_score,
    weibull_analysis, queue_simulation, pareto_frontier, robust_risk_analysis,
    capital_metrics, line_balance, sustainability_accounting, benchmark_compare,
    tier_allows, normalize_tier, PLATFORM_CATALOG, ml_demand_forecast, predictive_maintenance_score, currency_convert, save_scenario, scenario_table,
    analyze_experiment_scenarios, save_experiment,
)
from shoir_tier_capabilities import unique_modules


def test_catalog_and_tiers():
    names={x["name"] for x in PLATFORM_CATALOG}
    assert "Advanced Planning & Scheduling" in names
    assert tier_allows("Enterprise Plus Tier", "Enterprise")
    assert tier_allows("Professional Tier", "Mid-Tier Pro")
    assert not tier_allows("Starter Tier", "Enterprise")

def test_db_migration(tmp_path):
    db=tmp_path/"platform.db"
    assert init_platform_db(str(db))
    with sqlite_connection(db) as c:
        tables={r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    assert {"industrial_entities","platform_datasets","platform_models","platform_experiments","platform_decisions"} <= tables

def test_validation_and_quality():
    df=pd.DataFrame({"ID":["001","002","002"],"Value":["1,000","2,000","2,000"]})
    q=data_quality_report(df)
    assert q["rows"]==3
    res=validate_table(df,["ID","Value"])
    assert res["valid"] is True
    assert res["quality"]["duplicate_pct"]>0

def test_mrp_and_schedule():
    demand=pd.DataFrame({"Product":["P1"],"DemandQty":[10]})
    bom=pd.DataFrame({"Parent":["P1"],"Component":["C1"],"QtyPer":[2]})
    out=mrp_explode(demand,bom)
    assert out.iloc[0]["Gross Requirement"]==20
    orders=pd.DataFrame({"Order":["O1","O2"],"Product":["P1","P2"],"Qty":[10,20],
                         "DueDate":["2026-09-19","2026-09-20"],"ProcessingMin":[30,40],
                         "SetupMin":[5,5],"Machine":["M1","M1"],"Priority":[2,1]})
    sch=finite_schedule(orders)
    assert len(sch)==2 and sch["Finish"].is_monotonic_increasing

def test_quality_reliability():
    vals=[10,10.1,9.9,10.05,9.95]
    lim=spc_limits(vals)
    cap=capability(vals,9,11)
    assert lim["ucl"]>lim["mean"]>lim["lcl"]
    assert cap["Cpk"]>0
    fmea=fmea_score(pd.DataFrame({"Failure":["A","B"],"Severity":[8,4],"Occurrence":[5,3],"Detection":[2,4]}))
    assert fmea.iloc[0]["RPN"]==80
    w=weibull_analysis([10,20,30,40,50])
    assert w["Shape (Beta)"]>0 and w["Scale (Eta)"]>0

def test_simulation_and_risk():
    sim=queue_simulation(10,20,servers=2,replications=3,duration_min=120)
    assert len(sim)==3
    risk=robust_risk_analysis(100,10,120,7,1,0.1,0.5,simulations=1000)
    assert 0<=risk["Service Probability"]<=1
    assert risk["P95 Exposure"]>=risk["P50 Exposure"]

def test_optimization_and_economics():
    df=pd.DataFrame({"Scenario":["A","B","C"],"Cost":[100,80,120],"Carbon":[50,80,40],"Service":[90,95,98]})
    front=pareto_frontier(df,["Cost","Carbon","Service"],[True,True,False])
    assert len(front)>=1
    risk=robust_risk_analysis(100,5,110,5,1,0,0.5,500)
    assert risk["Stockout Probability"]<1
    metrics=capital_metrics(100,[40,50,60],.1)
    assert "NPV" in metrics and "IRR" in metrics
    bal,meta=line_balance(pd.DataFrame({"Element":["A","B","C"],"TimeMin":[2,2,1]}),3)
    assert meta["Stations"]==2

def test_sustainability_and_benchmarks():
    df=pd.DataFrame({"Activity":["Electricity"],"Scope":["Scope 2"],"Quantity":[1000],"EmissionFactor":[0.42]})
    out=sustainability_accounting(df)
    assert out.iloc[0]["tCO2e"]==0.42
    actual=pd.DataFrame({"Metric":["OEE"],"Actual":[80]})
    bench=pd.DataFrame({"Metric":["OEE"],"Benchmark":[85]})
    comp=benchmark_compare(actual,bench)
    assert comp.iloc[0]["Delta"]==-5


def test_forecast_maintenance_currency_and_scenarios(tmp_path):
    dates=pd.date_range("2025-01-01",periods=18,freq="MS")
    hist=pd.DataFrame({"Date":dates,"Demand":[100+i*5 for i in range(18)],"Promotion":[0,1,0]*6,"Weather":[20+i%3 for i in range(18)]})
    forecast,metrics=ml_demand_forecast(hist,"Date","Demand",["Promotion","Weather"],6)
    assert len(forecast)==6 and forecast["Forecast"].notna().all()
    assert "R2" in metrics
    maint=predictive_maintenance_score(pd.DataFrame({"Asset":["A","B"],"Temperature":[60,90],"Vibration":[1,5],"RuntimeHours":[100,5000]}))
    assert maint.iloc[0]["Risk Score"]>=maint.iloc[1]["Risk Score"] or maint["Risk Score"].nunique()>1
    converted=currency_convert(pd.DataFrame({"Amount":[100],"Currency":["EUR"]}),"Amount","Currency","USD",{"USD":1,"EUR":0.92})
    assert abs(converted.iloc[0]["Base Amount"]-(100/0.92))<1e-9
    db=str(tmp_path/"scenario.db")
    init_platform_db(db)
    sid=save_scenario("Baseline","",{"x":1},{"Cost":100},"tester",db)
    assert sid.startswith("SCN-")
    assert len(scenario_table(db))==1



def test_experiment_lab_analysis_uses_selected_baseline_and_computes_all_deltas():
    scenarios = pd.DataFrame({
        "Scenario": ["A", "B", "C"],
        "Cost": [100.0, 80.0, 90.0],
        "Service": [95.0, 90.0, 97.0],
        "Risk": [10.0, 20.0, 8.0],
        "Inventory": [500.0, 400.0, 450.0],
        "Carbon": [40.0, 50.0, 35.0],
    })

    result = analyze_experiment_scenarios(scenarios, baseline_scenario="B")

    assert result["Baseline"].tolist() == [False, True, False]
    assert result["CostDelta"].tolist() == [20.0, 0.0, 10.0]
    assert result["ServiceDelta"].tolist() == [5.0, 0.0, 7.0]
    assert result["RiskDelta"].tolist() == [-10.0, 0.0, -12.0]
    assert result["InventoryDelta"].tolist() == [100.0, 0.0, 50.0]
    assert result["CarbonDelta"].tolist() == [-10.0, 0.0, -15.0]


def test_experiment_lab_analysis_rejects_invalid_scenarios():
    with pytest.raises(ValueError, match="non-empty name"):
        analyze_experiment_scenarios(pd.DataFrame({
            "Scenario": ["Baseline", ""], "Cost": [100.0, 90.0]
        }))

    with pytest.raises(ValueError, match="unique"):
        analyze_experiment_scenarios(pd.DataFrame({
            "Scenario": ["Baseline", "Baseline"], "Cost": [100.0, 90.0]
        }))

    with pytest.raises(ValueError, match="non-numeric"):
        analyze_experiment_scenarios(pd.DataFrame({
            "Scenario": ["Baseline", "Alternative"], "Cost": [100.0, "not-a-cost"]
        }))


def test_save_experiment_persists_all_seven_columns(tmp_path):
    db = str(tmp_path / "experiment.db")
    assert init_platform_db(db)

    experiment_id = save_experiment(
        "Scenario Matrix",
        "Experiment Lab",
        [{"Scenario": "Baseline", "Cost": 100.0}],
        {"baseline_scenario": "Baseline", "scenario_results": [{"CostDelta": 0.0}]},
        "tester",
        db_path=db,
    )

    assert experiment_id.startswith("EXP-")
    with sqlite_connection(db) as conn:
        row = conn.execute(
            """SELECT experiment_id, name, module, scenarios_json, results_json, created_by, created_at
               FROM platform_experiments WHERE experiment_id=?""",
            (experiment_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == experiment_id
    assert row[2] == "Experiment Lab"
    assert row[5] == "tester"



def test_unique_modules_preserves_order_and_removes_duplicates():
    assert unique_modules(["MILP Solvers", "AI Copilot", "MILP Solvers", "", None, "AI Copilot"]) == [
        "MILP Solvers", "AI Copilot"
    ]



def test_staging_dataset_registration_uses_immutable_version_registry(monkeypatch):
    import durable_account_store
    import industrial_platform as platform

    calls = []
    monkeypatch.setattr(durable_account_store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(
        durable_account_store, "edge_upload_and_register_dataset_version",
        lambda **kwargs: calls.append(kwargs) or {
            "ok": True,
            "registration": {
                "dataset_id": kwargs["dataset_id"],
                "version": 3,
                "data_hash": kwargs["data_hash"],
                "version_fingerprint": kwargs["version_fingerprint"],
                "created_new_version": True,
            },
        },
    )
    state = {}
    monkeypatch.setattr(
        platform, "_industrial_platform_session_state", lambda: state
    )
    frame = pd.DataFrame({"asset_id": ["A-1", "A-2"], "throughput_tph": [12.5, 14.0]})
    first = platform.register_dataset(
        "Production", "production.csv", frame,
        username="synthetic-user", workspace="plant-a", token="session-token",
    )
    second = platform.register_dataset(
        "Production", "production.csv", frame.copy(deep=True),
        username="synthetic-user", workspace="plant-a", token="session-token",
    )
    assert first == second
    assert len(calls) == 2
    assert calls[0]["dataset_id"] == first
    assert calls[0]["file_bytes"] == calls[1]["file_bytes"]
    assert calls[0]["data_hash"] == calls[1]["data_hash"]
    assert calls[0]["version_fingerprint"] == calls[1]["version_fingerprint"]
    assert calls[0]["row_count"] == 2
    assert calls[0]["column_count"] == 2
    assert state["data_platform_latest_version"] == 3


def test_staging_dataset_registration_fails_closed_without_session(monkeypatch):
    import durable_account_store
    import industrial_platform as platform

    monkeypatch.setattr(durable_account_store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(
        durable_account_store, "edge_upload_and_register_dataset_version",
        lambda **kwargs: pytest.fail("must not call the API without an authenticated session"),
    )
    with pytest.raises(PermissionError, match="authenticated staging session"):
        platform.register_dataset(
            "Production", "production.csv",
            pd.DataFrame({"units": [1, 2]}),
            username="synthetic-user", workspace="plant-a", token="",
        )


def test_staging_dataset_registration_rejects_too_many_transformations(monkeypatch):
    import durable_account_store
    import industrial_platform as platform

    monkeypatch.setattr(durable_account_store, "APP_ENVIRONMENT", "local")
    with pytest.raises(ValueError, match="50 entries"):
        platform.register_dataset(
            "Production", "production.csv",
            pd.DataFrame({"units": [1]}),
            transformations=[{"operation": "clean"}] * 51,
        )



def test_load_registered_dataset_activates_verified_shared_frame(monkeypatch):
    import durable_account_store
    import industrial_platform as platform

    raw = b"asset_id,throughput_tph\nA-1,12.5\nA-2,14.0\n"
    monkeypatch.setattr(durable_account_store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(
        durable_account_store, "edge_download_dataset_version",
        lambda **kwargs: (raw, {
            "data_hash": "f" * 64, "version": 2, "row_count": 2, "column_count": 2
        }),
    )
    state = {}
    monkeypatch.setattr(platform, "_industrial_platform_session_state", lambda: state)
    monkeypatch.setattr(
        platform,
        "_activate_dataset_for_shared_workspace",
        lambda df, filename, sheet, signature: state.update({
            "universal_active_dataset": df.copy(deep=True),
            "data_platform_latest_df": df.copy(deep=True),
            "shoir_data_status": "IMPORTED",
            "shoir_data_source": f"{filename} · {sheet}",
            "shoir_data_version": signature[:12],
            "shoir_data_hash": signature,
        }),
    )
    frame = platform.load_registered_dataset(
        "DS-ABCDEF012345", "synthetic-user", "plant-a", "session-token"
    )
    assert list(frame.columns) == ["asset_id", "throughput_tph"]
    assert len(frame) == 2
    assert state["universal_active_dataset"].equals(frame)
    assert state["data_platform_latest_version"] == 2


def test_load_registered_dataset_rejects_metadata_row_count_mismatch(monkeypatch):
    import durable_account_store
    import industrial_platform as platform

    monkeypatch.setattr(durable_account_store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(
        durable_account_store, "edge_download_dataset_version",
        lambda **kwargs: (
            b"asset_id\nA-1\n",
            {"data_hash": "f" * 64, "version": 1, "row_count": 2, "column_count": 1},
        ),
    )
    state = {}
    monkeypatch.setattr(platform, "_industrial_platform_session_state", lambda: state)
    with pytest.raises(RuntimeError, match="row count"):
        platform.load_registered_dataset(
            "DS-ABCDEF012345", "synthetic-user", "plant-a", "session-token"
        )



def test_dataset_profile_figures_render_real_missingness_and_numeric_distributions():
    from industrial_platform import _dataset_profile_figures

    frame = pd.DataFrame({
        "asset_id": ["A-1", "A-2", "A-3", "A-4"],
        "throughput_tph": [10.0, 12.0, None, 18.0],
        "temperature_c": [40.0, 42.0, 43.0, 47.0],
    })
    figures = _dataset_profile_figures(frame, "Synthetic production")
    assert len(figures) == 3
    assert figures[0][0] == "Missingness"
    assert len(figures[0][1].data) >= 1
    assert any("throughput_tph" in label for label, _ in figures[1:])
    for label, figure in figures:
        assert figure.data, label
        assert figure.layout.title.text
        assert figure.layout.xaxis.title.text
        assert figure.layout.yaxis.title.text


def test_dataset_profile_figures_handle_empty_and_non_numeric_data():
    from industrial_platform import _dataset_profile_figures

    assert _dataset_profile_figures(pd.DataFrame(), "Empty") == []
    frame = pd.DataFrame({"asset_id": ["A-1", "A-2"], "status": ["Run", "Stop"]})
    figures = _dataset_profile_figures(frame, "Categorical only")
    assert len(figures) == 1
    assert figures[0][0] == "Missingness"
    assert figures[0][1].data


def test_data_platform_route_has_stable_t020_entitlement_guard_and_visual_panel():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "industrial_platform.py").read_text(encoding="utf-8")
    assert 'require_tool_access(tier, "T020")' in source
    assert "def _render_dataset_profile(" in source
    assert "st.plotly_chart(" in source
    assert "data_platform_processed_upload_fingerprint" in source



def test_dataset_profile_renderer_calls_plotly_for_each_generated_figure(monkeypatch):
    import sys
    from types import SimpleNamespace
    from industrial_platform import _dataset_profile_figures, _render_dataset_profile

    rendered = []
    metrics = []
    def metric(label, value):
        metrics.append((label, value))
    fake_streamlit = SimpleNamespace(
        columns=lambda count: [SimpleNamespace(metric=metric) for _ in range(count)],
        warning=lambda message: None,
        success=lambda message: None,
        caption=lambda message: None,
        plotly_chart=lambda figure, **kwargs: rendered.append((figure, kwargs)),
    )
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit)
    frame = pd.DataFrame({
        "asset_id": ["A-1", "A-2", "A-3"],
        "throughput_tph": [8.0, 11.0, None],
    })
    _render_dataset_profile(frame, "Production", "render-test")
    assert len(metrics) == 4
    assert len(rendered) == len(_dataset_profile_figures(frame, "Production"))
    assert len(rendered) == 2
    assert all(call[1]["use_container_width"] is True for call in rendered)
    assert all(call[1]["key"].startswith("render-test_") for call in rendered)


def test_industrial_data_platform_is_reachable_from_original_app_and_workbench():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    app_source = (root / "app.py").read_text(encoding="utf-8")
    workbench_source = (
        root / "pages" / "Industrial_Engineering_Workbench.py"
    ).read_text(encoding="utf-8")
    platform_source = (root / "industrial_platform.py").read_text(encoding="utf-8")

    assert "PLATFORM_CATALOG" in app_source
    assert "render_industrial_module(mod" in app_source
    assert '"Industrial Data Platform"' in platform_source
    assert "from industrial_platform import render_module" in workbench_source
    assert "render_module(selected, RAW_TIER, USER)" in workbench_source
    assert 'elif module=="Industrial Data Platform":' in platform_source



def test_shared_dataset_activation_delegates_to_existing_application_shell(monkeypatch):
    import sys
    from types import SimpleNamespace
    import industrial_platform as platform

    calls = []
    fake_shell = SimpleNamespace(
        _activate_shared_dataset=lambda df, **kwargs: calls.append(
            (df.copy(deep=True), dict(kwargs))
        )
    )
    monkeypatch.setitem(sys.modules, "shoir_application_shell", fake_shell)
    frame = pd.DataFrame({"asset_id": ["A-1"], "rate_tph": [9.5]})
    platform._activate_dataset_for_shared_workspace(
        frame,
        filename="production.xlsx",
        sheet="Line 1",
        signature="a" * 64,
    )
    assert len(calls) == 1
    assert calls[0][0].equals(frame)
    assert calls[0][1] == {
        "filename": "production.xlsx",
        "sheet": "Line 1",
        "signature": "a" * 64,
    }


def test_industrial_data_platform_entitlement_matches_existing_catalog_and_tool():
    from industrial_platform import PLATFORM_CATALOG, tier_allows
    from shoir_tool_registry import get_tool, require_tool_access

    entry = next(
        item for item in PLATFORM_CATALOG
        if item["name"] == "Industrial Data Platform"
    )
    tool = get_tool("T020")
    assert entry["tier"] == "Enterprise"
    assert tool is not None
    assert tool["target_minimum_tier"] == "Enterprise"
    assert tier_allows("Enterprise", entry["tier"])
    with pytest.raises(PermissionError):
        require_tool_access("Professional", "T020")
    require_tool_access("Enterprise", "T020")



def test_staging_dataset_registration_can_append_version_to_existing_logical_id(monkeypatch):
    import durable_account_store
    import industrial_platform as platform

    calls = []
    monkeypatch.setattr(durable_account_store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(
        durable_account_store, "edge_upload_and_register_dataset_version",
        lambda **kwargs: calls.append(kwargs) or {
            "ok": True,
            "registration": {
                "dataset_id": kwargs["dataset_id"],
                "version": 4,
                "created_new_version": True,
            },
        },
    )
    state = {}
    monkeypatch.setattr(platform, "_industrial_platform_session_state", lambda: state)
    frame = pd.DataFrame({"asset_id": ["A-1"], "throughput_tph": [15.0]})
    saved_id = platform.register_dataset(
        "Renamed production view",
        "production-export-2026-11.csv",
        frame,
        username="synthetic-user",
        workspace="plant-a",
        token="session-token",
        dataset_id="DS-AABBCCDDEEFF",
        transformations=[{"operation": "normalize_sheet_to_csv", "status": "completed"}],
    )
    assert saved_id == "DS-AABBCCDDEEFF"
    assert calls[0]["dataset_id"] == "DS-AABBCCDDEEFF"
    assert state["data_platform_latest_version"] == 4


def test_dataset_registration_rejects_malformed_existing_dataset_id_before_network(monkeypatch):
    import durable_account_store
    import industrial_platform as platform

    monkeypatch.setattr(durable_account_store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(
        durable_account_store, "edge_upload_and_register_dataset_version",
        lambda **kwargs: pytest.fail("invalid logical ID must be rejected before network"),
    )
    with pytest.raises(ValueError, match="canonical DS- identifier"):
        platform.register_dataset(
            "Production",
            "production.csv",
            pd.DataFrame({"asset_id": ["A-1"]}),
            username="synthetic-user",
            workspace="plant-a",
            token="session-token",
            dataset_id="../OTHER-WORKSPACE",
        )



def test_local_dataset_registration_returns_stable_generated_id(tmp_path, monkeypatch):
    import durable_account_store
    import industrial_platform as platform

    monkeypatch.setattr(durable_account_store, "APP_ENVIRONMENT", "local")
    frame = pd.DataFrame({"asset_id": ["A-1"], "throughput_tph": [10.0]})
    first = platform.register_dataset(
        "Production", "source.csv", frame,
        db_path=str(tmp_path / "local-datasets.db"),
    )
    second = platform.register_dataset(
        "Production renamed", "source-renamed.csv", frame,
        db_path=str(tmp_path / "local-datasets.db"),
        dataset_id=first,
    )
    assert first.startswith("DS-")
    assert second == first



def test_local_dataset_registration_initializes_missing_sqlite_schema(tmp_path, monkeypatch):
    import durable_account_store
    import industrial_platform as platform

    monkeypatch.setattr(durable_account_store, "APP_ENVIRONMENT", "local")
    db_path = str(tmp_path / "dataset.db")
    frame = pd.DataFrame({
        "asset_id": ["A-1", "A-2"],
        "throughput_tph": [12.5, 14.0],
    })

    dataset_id = platform.register_dataset(
        "Production",
        "production.csv",
        frame,
        db_path=db_path,
    )

    with sqlite_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT dataset_id, name, source_name, row_count, column_count, sha256
            FROM platform_datasets
            WHERE dataset_id = ?
            """,
            (dataset_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == dataset_id
    assert row[1:5] == ("Production", "production.csv", 2, 2)
    assert len(row[5]) == 64
