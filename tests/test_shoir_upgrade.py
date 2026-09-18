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

from shoir_upgrade import apply_excel_function, read_uploaded_workbook, build_workbook_bundle

def test_all_excel_functions_have_working_core_paths():
    df=pd.DataFrame({"Name":[" alice ","BOB "],"Value":["1,200","300"],"Text":["a-b","c-b"]})
    for fn in ["TRIM","CLEAN","UPPER","LOWER","PROPER","REMOVE DUPLICATES","VALUE","IFERROR"]:
        out,msg=apply_excel_function(df,fn,columns=list(df.columns))
        assert isinstance(out,pd.DataFrame)
        assert msg
    out,_=apply_excel_function(df,"TEXTSPLIT",column="Text",delimiter="-")
    assert "Text_1" in out.columns and "Text_2" in out.columns
    out,_=apply_excel_function(df,"TEXTJOIN",columns=["Name","Text"],delimiter="|",output_column="Joined")
    assert "Joined" in out.columns
    out,_=apply_excel_function(df,"SUBSTITUTE",old="b",new="B",columns=["Text"])
    assert "B" in out.loc[0,"Text"]
    out,_=apply_excel_function(df,"FIND & REPLACE",find_text="alice",replace_text="ALICE",columns=["Name"])
    assert out.loc[0,"Name"]==" alice "

def test_workbook_import_supports_csv():
    raw=b"Name,Value\nAlice,1\nBob,2\n"
    sheets=read_uploaded_workbook(raw,"sample.csv")
    assert list(sheets)==["CSV"]
    assert sheets["CSV"].shape==(2,2)

def test_workbook_bundle_contains_xlsx():
    data=build_workbook_bundle("Test",[("Data",pd.DataFrame({"Name":["A","B"],"Value":[1,2]}))])
    assert data[:2]==b"PK"
