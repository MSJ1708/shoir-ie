"""Balanced crossed Gauge R&R golden and validation cases for T033."""
import numpy as np
import pandas as pd
import pytest

from shoir_100_tool_msa_engine import analyze_crossed_gage_rr


def sample():
    rows=[]
    data={
      "P1":{"A":[9.8,10.0,10.2],"B":[9.9,10.1,10.0]},
      "P2":{"A":[19.8,20.2,20.0],"B":[20.1,20.0,19.9]},
      "P3":{"A":[29.7,30.0,30.3],"B":[30.2,30.1,29.8]},
    }
    for part,appraisers in data.items():
        for appraiser,values in appraisers.items():
            for measurement in values:
                rows.append({"part_id":part,"appraiser":appraiser,"measurement":measurement})
    return pd.DataFrame(rows)


def test_crossed_gage_rr_has_balanced_anova_and_nonnegative_components():
    result=analyze_crossed_gage_rr(sample(),part_col="part_id",appraiser_col="appraiser",measurement_col="measurement",tolerance_width=2.0)
    assert result["status"]=="CALCULATED"
    assert result["metrics"]["part_count"]==3
    assert result["metrics"]["appraiser_count"]==2
    assert result["metrics"]["replicates_per_cell"]==3
    assert result["metrics"]["reading_count"]==18
    comp=result["variance_components"].set_index("component")
    assert comp["variance_component"].ge(0).all()
    assert comp.loc["Repeatability","variance_component"] > 0
    assert comp.loc["Part-to-part","variance_component"] > comp.loc["Repeatability","variance_component"]
    assert comp["percent_tolerance"].notna().all()
    assert result["metrics"]["number_of_distinct_categories"] is not None


def test_crossed_gage_rr_anova_degrees_of_freedom_and_ss_reconcile():
    result=analyze_crossed_gage_rr(sample(),part_col="part_id",appraiser_col="appraiser",measurement_col="measurement")
    anova=result["anova_table"].set_index("source")
    assert anova.loc["Part","df"]==2
    assert anova.loc["Appraiser","df"]==1
    assert anova.loc["Part × Appraiser","df"]==2
    assert anova.loc["Repeatability/Error","df"]==12
    assert anova["sum_of_squares"].sum()==pytest.approx(((sample()["measurement"]-sample()["measurement"].mean())**2).sum())


def test_crossed_gage_rr_rejects_unbalanced_incomplete_and_bad_tolerance():
    frame=sample()
    with pytest.raises(ValueError,match="same number of replicates"):
        analyze_crossed_gage_rr(frame.drop(index=0),part_col="part_id",appraiser_col="appraiser",measurement_col="measurement")
    with pytest.raises(ValueError,match="(?i)at least two"):
        analyze_crossed_gage_rr(frame[frame["part_id"]=="P1"],part_col="part_id",appraiser_col="appraiser",measurement_col="measurement")
    with pytest.raises(ValueError,match="positive"):
        analyze_crossed_gage_rr(frame,part_col="part_id",appraiser_col="appraiser",measurement_col="measurement",tolerance_width=0)
    with pytest.raises(ValueError,match="Missing"):
        analyze_crossed_gage_rr(frame.iloc[:-1].assign(measurement=np.nan),part_col="part_id",appraiser_col="appraiser",measurement_col="measurement")
