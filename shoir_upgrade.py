"""Shoir-IE upgrade utilities: safe spreadsheet import, cleaning, reset snapshots and formatted exports."""
from __future__ import annotations
import io, re
from typing import Iterable, Optional, Tuple
import pandas as pd

def _norm(name) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())

def align_imported_table(imported: pd.DataFrame, target: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    if imported is None or not isinstance(imported, pd.DataFrame):
        raise ValueError("The uploaded file did not produce a valid table.")
    out = imported.copy()
    if out.columns.empty:
        raise ValueError("The uploaded file has no columns.")
    out.columns = [str(c).strip() for c in out.columns]
    if target is None or not isinstance(target, pd.DataFrame) or target.columns.empty:
        return out
    target_cols = list(target.columns)
    mapping = {}
    normalized = {_norm(c): c for c in out.columns}
    for col in target_cols:
        src = normalized.get(_norm(col))
        if src is not None:
            mapping[src] = col
    renamed = out.rename(columns=mapping)
    # Keep target schema first, then retain genuinely new imported columns.
    extras = [c for c in renamed.columns if c not in target_cols]
    for col in target_cols:
        if col not in renamed.columns:
            renamed[col] = pd.NA
    return renamed[target_cols + extras]

def clean_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, list]:
    if df is None:
        return pd.DataFrame(), []
    out = df.copy(deep=True)
    audit=[]
    before=len(out)
    out.columns=[str(c).strip() for c in out.columns]
    if len(out)!=before: audit.append({"action":"column_normalization","rows":len(out)})
    dup=int(out.duplicated().sum())
    if dup:
        out=out.drop_duplicates().reset_index(drop=True)
        audit.append({"action":"remove_duplicates","rows":dup})
    for col in out.columns:
        if pd.api.types.is_object_dtype(out[col]):
            original=out[col].copy()
            cleaned=out[col].map(lambda x: x.strip() if isinstance(x,str) else x)
            changed=int((original.fillna("").astype(str)!=cleaned.fillna("").astype(str)).sum())
            if changed: audit.append({"action":f"trim_whitespace:{col}","rows":changed})
            out[col]=cleaned
            # Convert only values that are consistently numeric; never invent values.
            numeric=pd.to_numeric(out[col].astype(str).str.replace(",","",regex=False), errors="coerce")
            nonblank=out[col].notna() & (out[col].astype(str).str.strip()!="")
            if int(nonblank.sum()) and float(numeric[nonblank].notna().mean())==1.0:
                out[col]=numeric
                audit.append({"action":f"numeric_normalization:{col}","rows":int(nonblank.sum())})
    return out, audit

def build_excel_report(title: str, tables: Iterable[Tuple[str,pd.DataFrame]], figures=None) -> bytes:
    figures = figures or []
    buf=io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        workbook=writer.book
        title_fmt=workbook.add_format({"bold":True,"font_size":18})
        header_fmt=workbook.add_format({"bold":True,"bg_color":"#1F4E78","font_color":"white","border":1})
        for i,(name,df) in enumerate(tables):
            sheet=re.sub(r"[^A-Za-z0-9_ ]+","",str(name))[:31] or f"Table{i+1}"
            safe=df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame(df)
            safe.to_excel(writer,index=False,sheet_name=sheet,startrow=2)
            ws=writer.sheets[sheet]
            ws.write(0,0,title,title_fmt)
            for j,col in enumerate(safe.columns):
                ws.write(2,j,col,header_fmt)
            ws.freeze_panes(3,0)
            ws.autofilter(2,0,2+len(safe),max(0,len(safe.columns)-1))
            for j,col in enumerate(safe.columns):
                vals=safe[col].astype(str) if not safe.empty else pd.Series(dtype=str)
                width=min(45,max(10,len(str(col))+2,int(vals.map(len).max()+2) if len(vals) else 10))
                ws.set_column(j,j,width)
    return buf.getvalue()
