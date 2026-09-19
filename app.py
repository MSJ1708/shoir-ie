from email.message import EmailMessage
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from PIL import Image
from scipy import stats
from shoir_upgrade import (align_imported_table, clean_dataframe, build_excel_report, build_workbook_bundle, read_uploaded_workbook, apply_excel_function, EXCEL_FUNCTIONS, copilot_module_recommendation)
from industrial_platform import PLATFORM_CATALOG, render_module as render_industrial_module, ml_demand_forecast, tier_allows as platform_tier_allows
from industrial_operating_system import render_industrial_operating_system
from industrial_experience import COPILOT_TOOLS, ensure_experience_db, feature_stats

# =====================================================================
# PAGE CONFIGURATION & CUSTOM CSS (Professional Styling & Hover Zoom)
# =====================================================================