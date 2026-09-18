import hashlib
import re
import html
import time
import smtplib
from email.message import EmailMessage
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from PIL import Image
from scipy import stats
from shoir_upgrade import (align_imported_table, clean_dataframe, build_excel_report, build_workbook_bundle, read_uploaded_workbook, apply_excel_function, EXCEL_FUNCTIONS, copilot_module_recommendation)
from industrial_platform import PLATFORM_CATALOG, render_module as render_industrial_module, ml_demand_forecast, tier_allows as platform_tier_allows
from industrial_operating_system import render_industrial_operating_system

# =====================================================================
# PAGE CONFIGURATION & CUSTOM CSS (Professional Styling & Hover Zoom)
# =====================================================================
st.set_page_config(
    page_title="shoir",
    page_icon="⚡",
    layout="wide"
)

st.markdown("""
<style>
    .main { background: linear-gradient(180deg,#f8fafc 0%,#ffffff 34%); }
    .block-container { max-width: 1480px; padding-top: 2rem; padding-bottom: 3rem; }
    section[data-testid="stSidebar"] { border-right: 1px solid #e2e8f0; }
    div.stButton > button, div[data-testid="stFormSubmitButton"] button {
        border-radius: 11px !important; border: 1px solid #cbd5e1 !important;
        min-height: 42px !important; font-weight: 700 !important;
        transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease !important;
    }
    div.stButton > button:hover, div[data-testid="stFormSubmitButton"] button:hover {
        transform: translateY(-1px); box-shadow: 0 8px 18px rgba(15,23,42,.10) !important;
        border-color: #2563eb !important;
    }
    div.stButton > button[kind="primary"] {
        border: 0 !important; background: linear-gradient(135deg,#2563eb,#0f766e) !important;
        color: white !important; box-shadow: 0 8px 18px rgba(37,99,235,.18) !important;
    }
    div[data-testid="stMetric"] {
        border: 1px solid #e2e8f0; border-radius: 14px; padding: 12px 14px;
        background: rgba(255,255,255,.88); box-shadow: 0 5px 18px rgba(15,23,42,.05);
    }
    div[data-testid="stExpander"] { border-radius: 14px; border-color: #e2e8f0; }
    .command-card { border:1px solid #e2e8f0; border-radius:18px; padding:20px; background:#fff; box-shadow:0 8px 28px rgba(15,23,42,.06); }
    .blue-metric {
        color: #0066cc !important;
        font-weight: 700;
    }
    div[data-testid="stMetricValue"] {
        color: #0066cc !important;
    }
    .api-card {
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
        padding: 20px;
        border-radius: 8px;
        margin-top: 10px;
    }
    .ticket-card {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border: 2px solid #0066cc;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
        cursor: pointer;
        margin-bottom: 15px;
    }