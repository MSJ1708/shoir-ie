"""Shoir-IE Excel/Copilot upgrade services.

Provides safe spreadsheet import, the 12 requested Excel-style cleaning functions,
reversible reset support, professional XLSX exports, and helper functions used by
the Streamlit Copilot.
"""
from __future__ import annotations
import io, re, zipfile, html
from datetime import datetime
from typing import Iterable, Optional, Tuple, Sequence
import pandas as pd
import numpy as np

EXCEL_FUNCTIONS = [
    ("TRIM", "Remove leading/trailing spaces and collapse repeated spaces."),
    ("CLEAN", "Remove non-printing control characters."),
    ("UPPER", "Convert text to uppercase."),
    ("LOWER", "Convert text to lowercase."),
    ("PROPER", "Convert text to title/proper case."),
    ("REMOVE DUPLICATES", "Remove duplicate rows."),
    ("TEXTSPLIT", "Split a text column into multiple columns by a delimiter."),
    ("TEXTJOIN", "Join selected columns into a new column."),
    ("SUBSTITUTE", "Replace text occurrences in selected columns."),
    ("FIND & REPLACE", "Find text and replace it in selected columns."),
    ("VALUE", "Convert numeric-looking text to numbers while protecting ID columns."),
    ("IFERROR", "Replace common Excel error tokens with blank/NA values."),
]

def _norm(name) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())

def _string_columns(df: pd.DataFrame) -> list[str]:
    return [str(c) for c in df.columns if pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c])]

def align_imported_table(imported: pd.DataFrame, target: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    if imported is None or not isinstance(imported, pd.DataFrame):
        raise ValueError("The uploaded file did not produce a valid table.")
    out = imported.copy(deep=True)
    if out.columns.empty:
        raise ValueError("The uploaded file has no columns.")
    out.columns = [str(c).strip() for c in out.columns]
    if target is None or not isinstance(target, pd.DataFrame) or target.columns.empty:
        return out
    target_cols = list(target.columns)
    normalized = {_norm(c): c for c in out.columns}
    mapping = {}
    for target_col in target_cols:
        source_col = normalized.get(_norm(target_col))
        if source_col is not None:
            mapping[source_col] = target_col
    renamed = out.rename(columns=mapping)
    extras = [c for c in renamed.columns if c not in target_cols]
    for col in target_cols:
        if col not in renamed.columns:
            renamed[col] = pd.NA
    return renamed[target_cols + extras]

def _safe_text_series(s: pd.Series) -> pd.Series:
    return s.map(lambda x: x.strip() if isinstance(x, str) else x)

def excel_trim(df: pd.DataFrame, columns: Optional[Sequence[str]] = None) -> pd.DataFrame:
    out=df.copy(deep=True); cols=list(columns) if columns else _string_columns(out)
    for c in cols:
        if c in out.columns: out[c]=out[c].map(lambda x: re.sub(r" +"," ",x).strip() if isinstance(x,str) else x)
    return out

def excel_clean(df: pd.DataFrame, columns: Optional[Sequence[str]] = None) -> pd.DataFrame:
    out=df.copy(deep=True); cols=list(columns) if columns else _string_columns(out)
    for c in cols:
        if c in out.columns: out[c]=out[c].map(lambda x: re.sub(r"[\x00-\x1F\x7F]","",x) if isinstance(x,str) else x)
    return out

def excel_upper(df: pd.DataFrame, columns: Optional[Sequence[str]] = None) -> pd.DataFrame:
    out=df.copy(deep=True); cols=list(columns) if columns else _string_columns(out)
    for c in cols:
        if c in out.columns: out[c]=out[c].map(lambda x: x.upper() if isinstance(x,str) else x)
    return out

def excel_lower(df: pd.DataFrame, columns: Optional[Sequence[str]] = None) -> pd.DataFrame:
    out=df.copy(deep=True); cols=list(columns) if columns else _string_columns(out)
    for c in cols:
        if c in out.columns: out[c]=out[c].map(lambda x: x.lower() if isinstance(x,str) else x)
    return out

def excel_proper(df: pd.DataFrame, columns: Optional[Sequence[str]] = None) -> pd.DataFrame:
    out=df.copy(deep=True); cols=list(columns) if columns else _string_columns(out)
    for c in cols:
        if c in out.columns: out[c]=out[c].map(lambda x: x.title() if isinstance(x,str) else x)
    return out

def excel_remove_duplicates(df: pd.DataFrame, subset: Optional[Sequence[str]] = None) -> pd.DataFrame:
    return df.copy(deep=True).drop_duplicates(subset=list(subset) if subset else None, keep="first").reset_index(drop=True)

def excel_textsplit(df: pd.DataFrame, column: str, delimiter: str = ",", maxsplit: int = -1) -> pd.DataFrame:
    if column not in df.columns: raise KeyError(f"Column not found: {column}")
    if not delimiter: raise ValueError("Delimiter must not be empty.")
    out=df.copy(deep=True)
    pieces=out[column].fillna("").astype(str).str.split(delimiter, n=maxsplit if maxsplit >= 0 else -1, expand=True)
    width=pieces.shape[1]
    for i in range(width):
        out[f"{column}_{i+1}"]=pieces.iloc[:,i].replace("",pd.NA)
    return out.drop(columns=[column])

def excel_textjoin(df: pd.DataFrame, columns: Sequence[str], delimiter: str = " ", output_column: str = "TextJoin") -> pd.DataFrame:
    cols=[c for c in columns if c in df.columns]
    if not cols: raise ValueError("Choose at least one existing column.")
    out=df.copy(deep=True)
    def join_row(row):
        vals=[str(row[c]).strip() for c in cols if pd.notna(row[c]) and str(row[c]).strip() not in ("","<NA>","nan")]
        return delimiter.join(vals)
    out[output_column]=out.apply(join_row,axis=1)
    return out

def _replace_in_columns(df: pd.DataFrame, old: str, new: str, columns: Optional[Sequence[str]]=None, instance_num: Optional[int]=None) -> pd.DataFrame:
    if old == "": raise ValueError("Find/replace text must not be empty.")
    out=df.copy(deep=True); cols=list(columns) if columns else _string_columns(out)
    for c in cols:
        if c not in out.columns: continue
        def repl(x):
            if not isinstance(x,str): return x
            if instance_num is None:
                return x.replace(old,new)
            start=0; count=0; result=[]
            while True:
                pos=x.find(old,start)
                if pos<0: result.append(x[start:]); break
                result.append(x[start:pos])
                count += 1
                result.append(new if count == instance_num else old)
                start=pos+len(old)
            return "".join(result)
        out[c]=out[c].map(repl)
    return out

def excel_substitute(df: pd.DataFrame, old: str, new: str, columns: Optional[Sequence[str]]=None, instance_num: Optional[int]=None) -> pd.DataFrame:
    return _replace_in_columns(df,old,new,columns,instance_num)

def excel_find_replace(df: pd.DataFrame, find_text: str, replace_text: str, columns: Optional[Sequence[str]]=None) -> pd.DataFrame:
    return _replace_in_columns(df,find_text,replace_text,columns,None)

def _looks_like_identifier(col: str, series: pd.Series) -> bool:
    sample=series.dropna().astype(str).str.strip()
    if sample.empty: return False
    return _norm(col) in {"id","sku","code","zip","zipcode","postalcode","partnumber","empid","employeeid"} or float(sample.str.match(r"^0\d+$").mean()) > .25

def excel_value(df: pd.DataFrame, columns: Optional[Sequence[str]]=None) -> pd.DataFrame:
    out=df.copy(deep=True); cols=list(columns) if columns else _string_columns(out)
    for c in cols:
        if c not in out.columns or _looks_like_identifier(c,out[c]): continue
        cleaned=out[c].astype("string").str.strip().str.replace(",","",regex=False)
        numeric=pd.to_numeric(cleaned,errors="coerce")
        nonblank=cleaned.notna() & (cleaned!="")
        if int(nonblank.sum()) and bool(numeric[nonblank].notna().all()):
            out[c]=numeric
    return out

EXCEL_ERROR_TOKENS=["#N/A","#VALUE!","#DIV/0!","#REF!","#NAME?","#NULL!","#NUM!"]

def excel_iferror(df: pd.DataFrame, columns: Optional[Sequence[str]]=None, replacement=pd.NA) -> pd.DataFrame:
    out=df.copy(deep=True); cols=list(columns) if columns else list(out.columns)
    for c in cols:
        if c in out.columns: out[c]=out[c].replace(EXCEL_ERROR_TOKENS,replacement)
    return out

def auto_clean_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame,list]:
    out=df.copy(deep=True); audit=[]
    old_cols=list(out.columns); out.columns=[str(c).strip() for c in out.columns]
    if old_cols != list(out.columns): audit.append({"function":"CLEAN","details":"Normalized column names"})
    before=out.copy(deep=True)
    out=excel_clean(out); out=excel_trim(out)
    if not out.equals(before): audit.append({"function":"CLEAN/TRIM","details":"Removed control characters and normalized whitespace"})
    out=excel_iferror(out)
    audit.append({"function":"IFERROR","details":"Replaced standard Excel error tokens"}) if any(v in EXCEL_ERROR_TOKENS for c in out.columns for v in out[c].astype(str).tolist()) else None
    before_n=len(out); out=excel_remove_duplicates(out)
    if len(out)!=before_n: audit.append({"function":"REMOVE DUPLICATES","details":f"Removed {before_n-len(out)} duplicate rows"})
    before_cols=out.copy(deep=True); out=excel_value(out)
    if not out.equals(before_cols): audit.append({"function":"VALUE","details":"Converted consistently numeric text columns"})
    return out,audit

def clean_dataframe(df: pd.DataFrame):
    """Backward-compatible name used by the Streamlit application."""
    return auto_clean_dataframe(df)

def apply_excel_function(df: pd.DataFrame, function_name: str, **kwargs) -> Tuple[pd.DataFrame,str]:
    fn=function_name.strip().upper()
    if fn=="TRIM": return excel_trim(df,kwargs.get("columns")),"TRIM applied"
    if fn=="CLEAN": return excel_clean(df,kwargs.get("columns")),"CLEAN applied"
    if fn=="UPPER": return excel_upper(df,kwargs.get("columns")),"UPPER applied"
    if fn=="LOWER": return excel_lower(df,kwargs.get("columns")),"LOWER applied"
    if fn=="PROPER": return excel_proper(df,kwargs.get("columns")),"PROPER applied"
    if fn=="REMOVE DUPLICATES": return excel_remove_duplicates(df,kwargs.get("columns")),"Duplicate rows removed"
    if fn=="TEXTSPLIT": return excel_textsplit(df,kwargs["column"],kwargs.get("delimiter",",")),"TEXTSPLIT applied"
    if fn=="TEXTJOIN": return excel_textjoin(df,kwargs["columns"],kwargs.get("delimiter"," "),kwargs.get("output_column","TextJoin")),"TEXTJOIN applied"
    if fn=="SUBSTITUTE": return excel_substitute(df,kwargs["old"],kwargs.get("new",""),kwargs.get("columns"),kwargs.get("instance_num")),"SUBSTITUTE applied"
    if fn=="FIND & REPLACE": return excel_find_replace(df,kwargs["find_text"],kwargs.get("replace_text",""),kwargs.get("columns")),"FIND & REPLACE applied"
    if fn=="VALUE": return excel_value(df,kwargs.get("columns")),"VALUE applied"
    if fn=="IFERROR": return excel_iferror(df,kwargs.get("columns"),kwargs.get("replacement",pd.NA)),"IFERROR applied"
    raise ValueError(f"Unsupported Excel function: {function_name}")

def read_uploaded_workbook(raw: bytes, filename: str) -> dict[str,pd.DataFrame]:
    if not raw: raise ValueError("The uploaded file is empty.")
    lower=filename.lower()
    if lower.endswith(".csv"):
        return {"CSV":pd.read_csv(io.BytesIO(raw))}
    if lower.endswith(".xlsx"):
        book=pd.ExcelFile(io.BytesIO(raw))
        return {sheet:pd.read_excel(io.BytesIO(raw),sheet_name=sheet) for sheet in book.sheet_names}
    raise ValueError("Upload an .xlsx or .csv file.")

def build_excel_report(title: str, tables: Iterable[Tuple[str,pd.DataFrame]], figures=None, audit=None, function_reference=True) -> bytes:
    figures=figures or []; audit=audit or []
    buf=io.BytesIO()
    with pd.ExcelWriter(buf,engine="xlsxwriter") as writer:
        workbook=writer.book
        title_fmt=workbook.add_format({"bold":True,"font_size":18,"font_color":"1E3A8A"})
        subtitle_fmt=workbook.add_format({"italic":True,"font_color":"64748B"})
        header_fmt=workbook.add_format({"bold":True,"bg_color":"1E3A8A","font_color":"white","border":1})
        for i,(name,df) in enumerate(tables):
            safe_name=re.sub(r"[^A-Za-z0-9_ ]+","",str(name))[:31] or f"Table{i+1}"
            safe=df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame(df)
            safe.to_excel(writer,index=False,sheet_name=safe_name,startrow=3)
            ws=writer.sheets[safe_name]
            ws.write(0,0,title,title_fmt)
            ws.write(1,0,f"Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",subtitle_fmt)
            for j,col in enumerate(safe.columns): ws.write(3,j,col,header_fmt)
            ws.freeze_panes(4,0)
            if len(safe.columns): ws.autofilter(3,0,3+len(safe),len(safe.columns)-1)
            numeric_cols=[i for i,col in enumerate(safe.columns) if pd.api.types.is_numeric_dtype(safe[col])]
            if numeric_cols and len(safe) > 0 and len(safe.columns) >= 2:
                chart=workbook.add_chart({"type":"column"})
                for i in numeric_cols:
                    chart.add_series({"name":[safe_name,3,i],"categories":[safe_name,4,0,3+len(safe),0],"values":[safe_name,4,i,3+len(safe),i]})
                chart.set_title({"name":f"{safe_name} — Numeric Metrics"})
                chart.set_x_axis({"name":str(safe.columns[0])})
                chart.set_y_axis({"name":"Value"})
                chart.set_legend({"position":"bottom"})
                ws.insert_chart(3,len(safe.columns)+2,chart,{"x_scale":1.25,"y_scale":1.1})
            for j,col in enumerate(safe.columns):
                vals=safe[col].astype(str) if not safe.empty else pd.Series(dtype=str)
                width=min(55,max(10,len(str(col))+2,int(vals.map(len).max()+2) if len(vals) else 10))
                ws.set_column(j,j,width)
        if audit:
            pd.DataFrame(audit).to_excel(writer,index=False,sheet_name="Cleaning Audit")
        if function_reference:
            ref=pd.DataFrame([{"Function":n,"Purpose":d} for n,d in EXCEL_FUNCTIONS])
            ref.to_excel(writer,index=False,sheet_name="Excel Functions")
            writer.sheets["Excel Functions"].freeze_panes(1,0)
    return buf.getvalue()

def build_workbook_bundle(title: str, tables: Iterable[Tuple[str,pd.DataFrame]], figures=None, audit=None) -> bytes:
    xlsx=build_excel_report(title,tables,figures,audit)
    bundle=io.BytesIO()
    with zipfile.ZipFile(bundle,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("shoir_ie_formatted_workbook.xlsx",xlsx)
        if figures:
            for idx,(label,fig) in enumerate(figures,1):
                try:
                    z.writestr(f"charts/chart_{idx}_{re.sub(r'[^A-Za-z0-9]+','_',str(label)).lower()}.html",fig.to_html(include_plotlyjs="cdn",full_html=True))
                except Exception:
                    pass
        readme=(
            f"Shoir-IE Report: {title}\n"
            "The XLSX contains formatted tables and cleaning audit information. "
            "The charts folder contains the exact interactive Plotly figures captured from the module when available.\n"
        )
        z.writestr("README.txt",readme)
    return bundle.getvalue()

def copilot_module_recommendation(prompt: str) -> str:
    p=str(prompt or "").lower()
    rules=[        (["demand forecasting","forecast sku","weather demand","promotion demand","macro demand"],"Advanced ML Demand Forecasting","Enterprise"),
        (["predictive maintenance","remaining useful life","rul telemetry","machine health"],"Advanced Predictive Maintenance","Enterprise Plus"),
        (["scenario version","baseline versus","side by side scenario","scenario delta"],"Scenario Versioning","Enterprise Plus"),
        (["3d factory","factory layout","3d layout","factory twin"],"3D Factory Designer","Enterprise Plus"),
        (["connector health","api connector","sap connector","oracle connector","wms connector"],"Industrial Connectivity Hub","Enterprise Plus"),
        (["executive pdf","board report","executive report"],"Executive Report Center","Enterprise"),
        (["currency conversion","local currency","trade compliance"],"Localization & Multi-Currency","Mid-Tier Pro"),
        (["role access","rbac","team permissions"],"Team Workspaces & RBAC","Enterprise"),

        (["aps","advanced planning","finite schedule","production schedule","capacity schedule"],"Advanced Planning & Scheduling (APS)","Enterprise Plus"),
        (["mes","manufacturing execution","work order execution","shop floor execution"],"Manufacturing Execution System (MES)","Enterprise Plus"),
        (["spc","cpk","process capability","quality engineering","reliability"],"Quality Engineering & Reliability","Enterprise Plus"),
        (["discrete event","queue simulation","factory simulation","simulation lab"],"Industrial Simulation Lab","Enterprise Plus"),
        (["pareto","multi objective","robust optimization","trade off"],"Multi-Objective & Robust Optimization","Enterprise Plus"),
        (["digital thread","industrial data model","shared industrial model"],"Industrial Digital Thread","Enterprise Plus"),
        (["opc ua","mqtt","industrial connectivity","iot connector"],"Industrial Connectivity Hub","Enterprise Plus"),
        (["capex","npv","irr","payback","workforce economics"],"Capital & Workforce Engineering","Enterprise Plus"),
        (["lca","life cycle assessment","scope 1","scope 2","scope 3"],"Industrial Sustainability & LCA","Enterprise Plus"),
        (["model registry","reproducibility","model version","audit trail"],"Enterprise Security & Model Governance","Enterprise Plus"),

        (["forecast","seasonality","promotion","weather","macro"],"Advanced ML Demand Forecasting","Enterprise"),
        (["monte carlo","stochastic","uncertainty","lead time variance","disruption"],"Stochastic & Monte Carlo Risk Modeling","Enterprise"),
        (["sap","oracle","erp","wms","api connector"],"ERP & WMS API Connectors","Enterprise"),
        (["multi echelon","meio"],"MEIO Matrix","Mid-Tier Pro"),
        (["carbon","esg","emissions"],"Carbon Accounting","Mid-Tier Pro"),
        (["scenario compare","scenario version","baseline vs"],"Scenario Versioning","Mid-Tier Pro"),
        (["workspace","rbac","team access","role based"],"Team Workspaces & RBAC","Enterprise"),
        (["board report","executive report","powerpoint","pdf report"],"Executive Report Center","Enterprise"),
        (["queue simulation","discrete event","machine starvation","des canvas"],"Interactive DES Simulation Canvas","Enterprise"),
        (["predictive maintenance","remaining useful life","rul","machine failure"],"Predictive Maintenance Digital Twin","Enterprise"),
        (["currency","multi currency","trade compliance"],"Localization & Multi-Currency","Mid-Tier Pro"),
        (["excel","spreadsheet","workbook","csv","clean table"],"Excel Data Cleaning & Import","Starter"),
    ]
    for keys,module,tier in rules:
        if any(k in p for k in keys):
            return f"Recommended module: **{module}**. Required tier: **{tier}**."
    return "I need a little more detail about the outcome you want. Describe the data or decision you are trying to improve."

