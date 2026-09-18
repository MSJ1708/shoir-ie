import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from shoir_upgrade import align_imported_table, clean_dataframe, build_excel_report

def test_alignment_preserves_schema_and_extra_columns():
    target=pd.DataFrame({"Customer":["A"],"Demand":[10],"lat":[24.7],"lon":[46.6]})
    imported=pd.DataFrame({"customer":["B"],"demand":["1,200"],"extra":["keep"]})
    out=align_imported_table(imported,target)
    assert list(out.columns)==["Customer","Demand","lat","lon","extra"]
    assert pd.isna(out.loc[0,"lat"]) and pd.isna(out.loc[0,"lon"])
    assert out.loc[0,"extra"]=="keep"

def test_cleaning_removes_duplicates_and_numeric_commas():
    df=pd.DataFrame({" Name ":[" A "," A "],"Demand":["1,200","1,200"]})
    cleaned,audit=clean_dataframe(df)
    assert len(cleaned)==1
    assert cleaned.columns.tolist()==["Name","Demand"]
    assert cleaned.iloc[0]["Name"]=="A"
    assert cleaned.iloc[0]["Demand"]==1200
    assert audit

def test_excel_report_is_real_xlsx():
    data=build_excel_report("Test",[("Data",pd.DataFrame({"A":[1,2]}))])
    assert data[:2]==b"PK"
