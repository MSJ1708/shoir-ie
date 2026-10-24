"""Golden, seed reproducibility and boundary tests for T071 discrete-event simulation."""
import pandas as pd
import pytest

from shoir_100_tool_simulation_engine import simulate_serial_flow_line


def test_deterministic_single_station_has_hand_calculable_flow_and_throughput():
    stations=pd.DataFrame([{"sequence":1,"station_id":"S1","servers":1,"mean_service_minutes":10.0,"service_time_cv":0.0}])
    result=simulate_serial_flow_line(stations,entity_count=10,mean_interarrival_minutes=5,
                                     arrival_pattern="fixed",warmup_entities=0,replications=1,random_seed=4)
    assert result["status"]=="SIMULATED"
    # With 10 entities, 10-minute service and 5-minute interarrival,
    # completion times are 10..100 and flow times are 10,15,...,55 for the first ten arrivals.
    assert result["entity_results"].iloc[0]["flow_time_minutes"]==pytest.approx(10)
    assert result["entity_results"].iloc[1]["flow_time_minutes"]==pytest.approx(15)
    assert result["replication_summary"].iloc[0]["throughput_units_per_hour"]==pytest.approx(10/100*60)
    assert result["metrics"]["live_data_connected"] is False


def test_simulation_is_reproducible_and_station_capacity_is_respected():
    stations=pd.DataFrame([
        {"sequence":1,"station_id":"Cut","servers":1,"mean_service_minutes":4.0,"service_time_cv":0.25},
        {"sequence":2,"station_id":"Pack","servers":2,"mean_service_minutes":5.0,"service_time_cv":0.1},
    ])
    a=simulate_serial_flow_line(stations,entity_count=80,mean_interarrival_minutes=3.0,
                                arrival_pattern="exponential",warmup_entities=10,replications=3,random_seed=44)
    b=simulate_serial_flow_line(stations,entity_count=80,mean_interarrival_minutes=3.0,
                                arrival_pattern="exponential",warmup_entities=10,replications=3,random_seed=44)
    pd.testing.assert_frame_equal(a["replication_summary"],b["replication_summary"])
    assert a["metrics"]["replications"]==3
    assert a["metrics"]["mean_flow_time_approx_95pct_t_interval"] is not None
    assert a["station_summary"]["average_utilization_percent"].between(0,100).all()


@pytest.mark.parametrize("kwargs,match",[
    ({"entity_count":9},"from 10 to 5000"),
    ({"warmup_entities":99},"leave at least two measured"),
    ({"replications":0},"from 1 to 20"),
    ({"mean_interarrival_minutes":0},"positive"),
])
def test_simulation_rejects_invalid_model_parameters(kwargs,match):
    stations=pd.DataFrame([{"sequence":1,"station_id":"S1","servers":1,"mean_service_minutes":1,"service_time_cv":0}])
    with pytest.raises(ValueError,match=match):
        simulate_serial_flow_line(stations,entity_count=100,mean_interarrival_minutes=5,warmup_entities=10,replications=2,**kwargs)


def test_simulation_rejects_duplicate_station_sequence_and_bad_service_distribution():
    with pytest.raises(ValueError,match="sequence numbers must be unique"):
        simulate_serial_flow_line(pd.DataFrame([
            {"sequence":1,"station_id":"A","servers":1,"mean_service_minutes":1,"service_time_cv":0},
            {"sequence":1,"station_id":"B","servers":1,"mean_service_minutes":1,"service_time_cv":0},
        ]),entity_count=20,warmup_entities=1)
    with pytest.raises(ValueError,match="CV must be between 0 and 3"):
        simulate_serial_flow_line(pd.DataFrame([{"sequence":1,"station_id":"A","servers":1,"mean_service_minutes":1,"service_time_cv":5}]),entity_count=20,warmup_entities=1)
