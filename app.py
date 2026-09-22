import streamlit as st
import pulp
import math
import folium
from streamlit_folium import st_folium
import sqlite3
import json
import datetime
import random
import string
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
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
from industrial_experience import COPILOT_TOOLS, ensure_experience_db, feature_stats, load_research_protocol, list_research_studies
from industrial_excellence_hub import render_platform_excellence_hub
from workspace_persistence import ensure_workspace_state_db, load_user_workspace, save_user_workspace
from durable_account_store import durable_backend_configured, sync_durable_accounts, upsert_remote_account, insert_remote_request, update_remote_request_status, account_is_expired, renewed_expiry

# =====================================================================
# PAGE CONFIGURATION & CUSTOM CSS (Professional Styling & Hover Zoom)
# =====================================================================
st.set_page_config(
    page_title="shoir",
    page_icon="⚡",
    layout="wide"
)

st.markdown("""
<div class="hero-card">
  <div class="kicker">Industrial Decision Platform</div>
  <div class="hero-title">🏭 Shoir-IE Industrial Engineering Command Center</div>
  <div class="hero-copy">Analyze → visualize → understand → decide → export. Results stay front and center; technical details remain available when needed.</div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<style>
    .main { background: linear-gradient(180deg,#f8fafc 0%,#ffffff 42%); }
    .block-container { max-width: 1500px; padding-top: 1.5rem; padding-bottom: 3rem; }
    section[data-testid="stSidebar"] { border-right: 1px solid #e2e8f0; }
    div[data-testid="stMetric"] { border: 1px solid #e2e8f0; border-radius: 14px; padding: 12px 14px; background: #fff; box-shadow: 0 6px 20px rgba(15,23,42,.05); }
    div.stButton > button, div[data-testid="stFormSubmitButton"] button { border-radius: 11px !important; min-height: 42px !important; font-weight: 700 !important; transition: .18s ease !important; }
    div.stButton > button:hover, div[data-testid="stFormSubmitButton"] button:hover { transform: translateY(-1px); box-shadow: 0 8px 18px rgba(15,23,42,.10) !important; border-color: #2563eb !important; }
    div.stButton > button[kind="primary"] { border: 0 !important; background: linear-gradient(135deg,#2563eb,#0f766e) !important; color: white !important; }
    div[data-testid="stExpander"] { border-radius: 14px; border-color: #e2e8f0; }
    .module-card { border:1px solid #dbe4f0; border-radius:16px; padding:14px 16px; background:#fff; box-shadow:0 5px 18px rgba(15,23,42,.04); margin-top:8px; }
    .result-card { border:1px solid #dbeafe; border-radius:16px; padding:15px 17px; background:linear-gradient(135deg,#f8fbff,#fff); box-shadow:0 5px 18px rgba(15,23,42,.04); }
    .hero-card { border:1px solid #dbe4f0; border-radius:20px; padding:22px 24px; background:linear-gradient(135deg,#f8fbff,#fff 58%,#f0fdfa); box-shadow:0 10px 30px rgba(15,23,42,.06); margin-bottom:18px; }
    .kicker { font-size:11px; font-weight:800; letter-spacing:.09em; text-transform:uppercase; color:#0f766e; }
    .hero-title { font-size:30px; font-weight:850; color:#0f172a; margin:3px 0; }
    .hero-copy { color:#64748b; font-size:14px; }
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
    .ticket-card:hover {
        transform: scale(0.96);
        box-shadow: 0 8px 20px rgba(0, 102, 204, 0.2);
    }
    .trust-banner {
        background-color: #f0f2f6;
        padding: 12px;
        border-radius: 6px;
        text-align: center;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

os.makedirs("payment_proofs", exist_ok=True)

# =====================================================================
# SQLITE ENTERPRISE DATABASE SETUP & AUTO-MIGRATION
# ---------------------------------------------------------------------
# NOTE: this file previously had THREE separate copies of the page-config
# / database-setup / login-and-register section stacked on top of each
# other (leftover from earlier edits that were never cleaned up). That
# caused several concrete bugs:
#   - st.set_page_config() was called 3 times (Streamlit only allows 1).
#   - init_db() was defined twice; the second, much simpler definition
#     silently overrode the first, so the admin account, audit_trail
#     table, and several enterprise_users columns the rest of the app
#     relies on were never actually created.
#   - The register tab was rendered twice (once via a leftover, unused
#     tab object), which is why the register/login tabs looked broken.
# This is now a single, consolidated version. No feature was removed.
# =====================================================================
def init_db():
    with sqlite3.connect("enterprise_full_workspace.db") as conn:
        cursor = conn.cursor()

        # 1. Saved Projects Table (Stores workspace / simulation states)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_projects (
                name TEXT PRIMARY KEY,
                data TEXT,
                updated_at TEXT
            )
        """)

        # 2. Enterprise Users Table (Stores user profiles, roles, and tier levels)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS enterprise_users (
                username TEXT PRIMARY KEY,
                password_hash TEXT,
                role TEXT,
                tier TEXT DEFAULT 'Starter Tier',
                email TEXT,
                trial_expires TEXT,
                linkedin TEXT,
                github TEXT,
                about_me TEXT,
                affiliate_code TEXT,
                ticket_expiry TEXT
            )
        """)

        # Auto-migrate missing columns safely if updating an existing database
        migrations = [
            ("tier", "TEXT DEFAULT 'Starter Tier'"),
            ("email", "TEXT"),
            ("trial_expires", "TEXT"),
            ("linkedin", "TEXT"),
            ("github", "TEXT"),
            ("about_me", "TEXT"),
            ("affiliate_code", "TEXT"),
            ("ticket_expiry", "TEXT")
        ]
        for col, defn in migrations:
            try:
                cursor.execute(f"ALTER TABLE enterprise_users ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass

        # 3. Login Credentials Table (this is what "Sign In" actually checks)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                password TEXT,
                role TEXT,
                tier TEXT,
                email TEXT,
                created_at TEXT,
                subscription_expires_at TEXT
            )
        """)

        try:
            cursor.execute("ALTER TABLE users ADD COLUMN subscription_expires_at TEXT")
        except sqlite3.OperationalError:
            pass
        cursor.execute("""
            UPDATE users
            SET subscription_expires_at = datetime(created_at, '+30 days')
            WHERE (subscription_expires_at IS NULL OR subscription_expires_at = '')
              AND created_at IS NOT NULL
              AND LOWER(username) <> 'sho'
        """)

        # 4. License Codes Table (Stores generated tier subscription keys)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS license_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                tier TEXT,
                duration_days INTEGER DEFAULT 30,
                is_used INTEGER DEFAULT 0,
                created_at TEXT
            )
        """)
        for col, defn in [("duration_days", "INTEGER DEFAULT 30"), ("is_used", "INTEGER DEFAULT 0"), ("created_at", "TEXT")]:
            try:
                cursor.execute(f"ALTER TABLE license_codes ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass

        # 5. Affiliate Referrals Table (Tracks user referral links and discounts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS affiliate_referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer TEXT,
                referred_user TEXT,
                discount_applied INTEGER DEFAULT 1,
                timestamp TEXT
            )
        """)

        # 6. Audit Trail Table (Tracks administrative actions and security events)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_trail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                user TEXT,
                action TEXT
            )
        """)

        # 7. Pending Payment / Ticket Requests Table
        #    (this is what "Send Verification Request" on the register tab
        #    writes to, and what the Admin Panel's "Pending Payment & Ticket
        #    Requests" section reads from)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                password TEXT,
                email TEXT,
                tier TEXT,
                payment_method TEXT,
                transaction_id TEXT,
                screenshot_path TEXT,
                status TEXT,
                timestamp TEXT
            )
        """)

        try:
            cursor.execute("ALTER TABLE pending_payments ADD COLUMN request_type TEXT DEFAULT 'New'")
        except sqlite3.OperationalError:
            pass

        # 8. System Settings Table (Stores global free-mode toggle)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES ('free_mode', 'off')")

        # 9. SECURITY: Login Attempts Table - backs the rate limiter below.
        # Stored in the database (not st.session_state) so a lockout can't
        # be bypassed just by opening a new tab / incognito window.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                success INTEGER,
                attempted_at TEXT
            )
        """)

        # 10. Seed Admin User 'sho' profile row
        # SECURITY FIX: the admin password used to be hardcoded directly in
        # this file as plain text (and hashed here with a bare, unsalted
        # SHA-256 - fast to brute-force by design, not meant for passwords).
        # It now reads from Streamlit secrets first. Add this to your
        # .streamlit/secrets.toml (same file your email credentials already
        # live in):
        #   [admin]
        #   password = "your-password-here"
        # Until you do, it falls back to the exact same password that was
        # already hardcoded here, so sho's login does not change today.
        # IMPORTANT: since that password has been sitting in plain text in
        # this file, if this project has ever been pushed to git (even a
        # private repo) or shared anywhere, treat it as compromised and
        # change it via secrets.toml.
        try:
            admin_password = st.secrets["admin"]["password"]
        except Exception:
            admin_password = "mohammedsuhail172008chennai!"
        admin_pass_hash = hash_password(admin_password)
        cursor.execute("""
            INSERT OR REPLACE INTO enterprise_users
            (username, password_hash, role, tier, email, trial_expires, affiliate_code, ticket_expiry)
            VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT affiliate_code FROM enterprise_users WHERE username = 'sho'), 'AFF-SHO-15'), ?)
        """, (
            "sho",
            admin_pass_hash,
            "Enterprise Admin",
            "Enterprise Tier",
            "mohsuhailji@gmail.com",
            "2030-01-01T00:00:00",
            "2030-01-01T00:00:00"
        ))

        # 11. Seed Admin User 'sho' login credentials (this is what Sign In checks)
        # SECURITY FIX: password is now stored hashed (salted PBKDF2), not
        # plain text. sho still logs in with the exact same password as
        # before - only the stored value's format changed.
        cursor.execute("DELETE FROM users WHERE LOWER(username) = 'sho'")
        cursor.execute("""
            INSERT INTO users (username, password, role, tier, email, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, ("sho", admin_pass_hash, "admin", "Enterprise Tier ($199)", "shoirtheagent@gmail.com", "2020-01-01T00:00:00"))

        conn.commit()

# =====================================================================
# SECURITY HELPERS
# =====================================================================
def hash_password(password, salt=None):
    """Salted PBKDF2-HMAC-SHA256 password hashing. Returns 'salt$hash'
    (both hex-encoded). 200,000 iterations, matching current OWASP
    guidance for PBKDF2-SHA256."""
    if salt is None:
        salt = os.urandom(16).hex()
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000).hex()
    return f"{salt}${pwd_hash}"

def verify_password(stored, provided):
    """Checks a password against a stored value. Understands the new
    salted-hash format ('salt$hash') and also accepts the old plain-text
    format so any account created before this update - including sho's -
    keeps working without anyone needing to reset a password. Returns
    (is_valid, needs_upgrade) - needs_upgrade is True for a legacy
    plaintext row that just matched, so the caller can transparently
    re-hash it."""
    if not stored or not provided:
        return False, False
    if "$" in stored:
        salt, _ = stored.split("$", 1)
        return (hash_password(provided, salt) == stored), False
    # Legacy plaintext row from before hashing was added
    return (stored == provided), (stored == provided)

def is_login_rate_limited(username, max_attempts=5, window_minutes=10):
    """SECURITY: basic brute-force throttle. Blocks further sign-in
    attempts for a username after too many failures in a short window.
    Backed by the login_attempts table (survives across tabs/sessions)."""
    try:
        conn = sqlite3.connect("enterprise_full_workspace.db")
        cursor = conn.cursor()