import inspect

import pandas as pd

import shoir_command_center_21 as cc


def _default():
    return cc.demo._default_inputs()


def test_dynamic_rescue_preserves_flagship_demo_economics():
    rescue = cc._dynamic_rescue(_default())
    assert rescue["baseline"]["Financial exposure SAR"] == 1_520_000.0
    assert rescue["intervention"]["Financial exposure SAR"] == 210_000.0
    assert rescue["baseline"]["Production shortfall %"] == 9.4
    assert rescue["intervention"]["Production shortfall %"] == 0.8
    assert rescue["baseline"]["Unplanned downtime h"] == 14.2
    assert rescue["intervention"]["Unplanned downtime h"] == 3.1
    assert rescue["intervention"]["Overtime SAR"] == 29_000.0
    assert rescue["intervention"]["Energy change %"] == 2.4


def test_dynamic_rescue_changes_with_scenario_inputs():
    base = cc._dynamic_rescue(_default())
    changed = _default()
    changed["production_oee"] = 62.0
    changed["maintenance_risk"] = 97.0
    changed["supplier_delay_h"] = 48.0
    changed["inventory_cover"] = 0.8
    changed_result = cc._dynamic_rescue(changed)

    assert changed_result["severity"] > base["severity"]
    assert changed_result["baseline"]["Financial exposure SAR"] > base["baseline"]["Financial exposure SAR"]
    assert changed_result["baseline"]["Unplanned downtime h"] > base["baseline"]["Unplanned downtime h"]


def test_policy_alternatives_are_configurable_and_complete():
    cc._ui_set("cost_weight", 25.0)
    cc._ui_set("risk_weight", 30.0)
    cc._ui_set("service_weight", 35.0)
    cc._ui_set("carbon_weight", 10.0)
    cc._ui_set("service_target", 95.0)
    alternatives = cc._policy_alternatives(_default())

    assert set(alternatives["Alternative"]) == {
        "Do Nothing",
        "Preventive Rescue",
        "Reroute + Rescue",
        "Capacity Expansion",
    }
    assert "Policy score" in alternatives.columns
    assert alternatives["Policy score"].notna().all()


def test_spatial_map_and_entity_model_cover_the_whole_demo_thread():
    assert len(cc.FLOOR) >= 8
    assert len(cc.ENTITY_POINTS) == 12
    assert {"C-204", "LINE-02", "MAT-BRG-08", "WO-4821", "OUT-72H"} <= set(cc.ENTITY_POINTS)
    fig = cc._build_floor_map()
    custom_traces = [trace for trace in fig.data if getattr(trace, "customdata", None) is not None]
    assert len(custom_traces) >= len(cc.FLOOR)
    assert any(
        any(str(item[0]) == "ENTITY" for item in (trace.customdata or []) if isinstance(item, (list, tuple)))
        for trace in custom_traces
    )


def test_role_workspaces_exist_for_every_supported_role():
    for role in cc.ROLE_OPTIONS:
        title, subtitle, metrics, actions = cc._role_data(role)
        assert title
        assert subtitle
        assert len(metrics) == 4
        assert len(actions) >= 3


def test_command_center_21_uses_native_interaction_support_when_available():
    assert cc._supports_kw(cc.st.plotly_chart, "on_select")
    assert cc._supports_kw(cc.st.button, "shortcut")


def test_route_points_to_the_new_upgrade_layer():
    source = inspect.getsource(cc.demo)
    assert "Industrial Control Center" in source
    platform_source = open("industrial_platform.py", encoding="utf-8").read()
    assert "from shoir_command_center_21 import render_investor_control_center_21" in platform_source
    assert 'render_investor_control_center_21(tier, username)' in platform_source


def test_upgrade_source_contains_all_seven_depth_upgrades():
    source = inspect.getsource(cc)
    required = [
        "shortcut",
        "_build_thread_graph",
        "_build_floor_map",
        "Persistent Inspector",
        "ROLE_OPTIONS",
        "_dynamic_rescue_model",
        "Financial re-evaluation",
        "Intervention alternatives",
    ]
    missing = [x for x in required if x not in source]
    assert not missing, missing


def test_customization_defaults_are_complete():
    cfg = cc._default_custom_config()
    assert cfg["facility_name"]
    assert {"Zone","Domain","X","Y","Width","Height"} <= set(cfg["zones"].columns)
    assert {"ID","Name","Domain","Priority"} <= set(cfg["assets"].columns)
    assert {"From","To","Relationship"} <= set(cfg["connections"].columns)
    assert {"KPI","Target","Unit","Operator","Domain"} <= set(cfg["kpis"].columns)
    assert {"Action","Command","Description"} <= set(cfg["actions"].columns)


def test_custom_zones_drive_spatial_map():
    old = cc.st.session_state.get(f"{cc.CC21_KEY}_custom_config")
    try:
        cfg = cc._default_custom_config()
        cfg["zones"] = pd.DataFrame(
            [["Custom Assembly","Production",10,10,30,20]],
            columns=["Zone","Domain","X","Y","Width","Height"],
        )
        cc.st.session_state[f"{cc.CC21_KEY}_custom_config"] = cfg
        assert "Custom Assembly" in cc._custom_zones()
        fig = cc._build_floor_map()
        assert any("Custom Assembly" in str(getattr(t,"text","")) for t in fig.data)
    finally:
        if old is None:
            cc.st.session_state.pop(f"{cc.CC21_KEY}_custom_config",None)
        else:
            cc.st.session_state[f"{cc.CC21_KEY}_custom_config"] = old

 
 
def test_custom_zone_health_falls_back_instead_of_crashing():
    old = cc.st.session_state.get(f"{cc.CC21_KEY}_custom_config")
    try:
        cfg = cc._default_custom_config()
        cfg["zones"] = pd.DataFrame(
            [["Investor Demo Extension", "Production", 10, 10, 20, 15]],
            columns=["Zone","Domain","X","Y","Width","Height"],
        )
        cc.st.session_state[f"{cc.CC21_KEY}_custom_config"] = cfg
        fig = cc._build_floor_map()
        assert any("Investor Demo Extension" in str(getattr(t, "text", "")) for t in fig.data)
    finally:
        if old is None:
            cc.st.session_state.pop(f"{cc.CC21_KEY}_custom_config", None)
        else:
            cc.st.session_state[f"{cc.CC21_KEY}_custom_config"] = old


def test_custom_assets_are_spatially_rendered():
    old = cc.st.session_state.get(f"{cc.CC21_KEY}_custom_config")
    try:
        cfg = cc._default_custom_config()
        cfg["assets"] = pd.DataFrame(
            [["INV-001", "Investor Showcase Asset", "Production", "High", "Production Line 1", 35, 60]],
            columns=["ID","Name","Domain","Priority","Zone","X","Y"],
        )
        cc.st.session_state[f"{cc.CC21_KEY}_custom_config"] = cfg
        fig = cc._build_floor_map()
        assert any("INV-001" in str(getattr(t, "name", "")) for t in fig.data)
    finally:
        if old is None:
            cc.st.session_state.pop(f"{cc.CC21_KEY}_custom_config", None)
        else:
            cc.st.session_state[f"{cc.CC21_KEY}_custom_config"] = old



def test_platform_router_has_command_center_fail_open_boundary():
    import pathlib
    source = pathlib.Path("industrial_platform.py").read_text(encoding="utf-8")
    marker = 'elif module=="Industrial Control Center":'
    idx = source.find(marker)
    assert idx >= 0
    section = source[idx:idx + 1800]
    assert "render_investor_control_center_21(tier, username)" in section
    assert "_render_customization()" in section
    assert "Command Center diagnostic" in section
