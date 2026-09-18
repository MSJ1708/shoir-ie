import os, sys, sqlite3, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
from shoir_upgrade import clean_dataframe, ensure_upgrade_schema, tier_allows, build_excel_report

def test_clean_dataframe_preserves_leading_zero_ids_and_removes_duplicates():
    df=pd.DataFrame({"SKU":["001","001","002"],"Sales":["1,200","1,200","900"],"Blank":[None,None,None]})
    out,audit=clean_dataframe(df)
    assert list(out["SKU"])==["001","002"]
    assert float(out["Sales"].iloc[0])==1200
    assert "Blank" not in out.columns

def test_migration_is_additive_and_idempotent():
    with tempfile.TemporaryDirectory() as d:
        db=os.path.join(d,"x.db")
        with sqlite3.connect(db) as c:
            c.execute("create table users(id integer primary key, username text)")
            c.execute("insert into users(username) values('existing')")
            c.commit()
        assert ensure_upgrade_schema(db) is True
        assert ensure_upgrade_schema(db) is True
        with sqlite3.connect(db) as c:
            assert c.execute("select username from users").fetchone()[0]=="existing"
            assert c.execute("pragma quick_check").fetchone()[0]=="ok"

def test_report_has_excel_container():
    data=build_excel_report("Test",[("Data",pd.DataFrame({"A":[1,2]}))],[])
    assert data[:2]==b"PK"

def test_tier_gating():
    assert tier_allows("Starter Tier","Starter")
    assert tier_allows("Enterprise Tier","Enterprise")
    assert not tier_allows("Mid-Tier Pro","Enterprise")
