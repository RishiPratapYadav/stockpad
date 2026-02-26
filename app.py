import streamlit as st
from supabase import create_client, Client
import pandas as pd
import requests
from datetime import datetime

st.set_page_config(page_title="StockPad", page_icon="◈", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@600;700&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Mono', monospace; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
.sp-logo { font-family: 'IBM Plex Sans', sans-serif; font-size: 26px; font-weight: 700; letter-spacing: 3px; color: #d8e0f0; }
.sp-logo span { color: #3d7eff; }
.sp-sub { font-size: 10px; color: #3a4060; letter-spacing: 4px; margin-bottom: 3px; }
hr { border-color: #1c2030 !important; }
section[data-testid="stSidebar"] { background: #0d0f1a; border-right: 1px solid #1e2235; }
section[data-testid="stSidebar"] label { font-size: 12px !important; color: #8090b0 !important; }
section[data-testid="stSidebar"] .stCheckbox label { color: #c0cce0 !important; font-size: 11px !important; }
</style>
""", unsafe_allow_html=True)

# ── Supabase ──────────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
supabase = get_supabase()

# ── Finnhub ───────────────────────────────────────────────────────────────────
FINNHUB_KEY  = st.secrets["FINNHUB_KEY"]
FINNHUB_BASE = "https://finnhub.io/api/v1"

def finnhub_get(endpoint, params):
    params["token"] = FINNHUB_KEY
    r = requests.get(f"{FINNHUB_BASE}/{endpoint}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()

SENTIMENTS = ["", "🟢 Bullish", "🔴 Bearish", "🟡 Neutral", "⚪ Watching"]

# ── Column Registry ───────────────────────────────────────────────────────────
# Each entry: (col_label, raw_key, api_source, format_fn, col_header, width)
# api_source: "quote" | "profile" | "metrics" | "user" | "fixed"
# "fixed" = always shown (Ticker, Name), "user" = always shown editable fields

def fmt_price(v):  return f"${float(v):,.2f}" if v is not None else "—"
def fmt_cap(v):
    if not v: return "—"
    v = float(v)
    if v >= 1e12: return f"${v/1e12:.2f}T"
    if v >= 1e9:  return f"${v/1e9:.2f}B"
    if v >= 1e6:  return f"${v/1e6:.0f}M"
    return str(v)
def fmt_pct(v):
    if v is None: return "—"
    sign = "+" if float(v) >= 0 else ""
    return f"{sign}{float(v):.2f}%"
def fmt_x(v):   return f"{float(v):.2f}x" if v is not None else "—"
def fmt_num(v): return f"{float(v):.2f}"   if v is not None else "—"
def fmt_str(v): return str(v) if v else "—"

# Groups: (group_label, [(col_label, db_key, api_source, fmt_fn, header, width), ...])
COLUMN_GROUPS = [
    ("📈 Price & Market", [
        ("Name",        "name",        "profile",  fmt_str,   "NAME",        "medium"),
        ("Sector",      "sector",      "profile",  fmt_str,   "SECTOR",      "medium"),
        ("Industry",    "industry",    "profile",  fmt_str,   "INDUSTRY",    "medium"),
        ("% Change",    "change_pct",  "quote",    fmt_pct,   "% CHG",       "small"),
        ("Mkt Cap",     "market_cap",  "profile",  fmt_str,   "MKT CAP",     "small"),
    ]),
    ("📊 Valuation", [
        ("P/E Ratio",   "pe_ratio",    "metrics",  fmt_x,     "P/E",         "small"),
        ("P/B Ratio",   "pb_ratio",    "metrics",  fmt_x,     "P/B",         "small"),
        ("P/S Ratio",   "ps_ratio",    "metrics",  fmt_x,     "P/S",         "small"),
    ]),
    ("📅 52-Week", [
        ("52W High",    "week52_high", "metrics",  fmt_price, "52W HIGH",    "small"),
        ("52W Low",     "week52_low",  "metrics",  fmt_price, "52W LOW",     "small"),
        ("52W Return",  "week52_return","metrics", fmt_pct,   "52W RETURN",  "small"),
    ]),
    ("⚖️ Risk", [
        ("Beta",        "beta",        "metrics",  fmt_num,   "BETA",        "small"),
        ("Debt/Equity", "debt_equity", "metrics",  fmt_num,   "DEBT/EQ",     "small"),
        ("Curr Ratio",  "current_ratio","metrics", fmt_num,   "CURR RATIO",  "small"),
    ]),
    ("💰 Income & Returns", [
        ("Div Yield",   "dividend_yield","metrics",fmt_pct,   "DIV YIELD",   "small"),
        ("ROE",         "roe",         "metrics",  fmt_pct,   "ROE",         "small"),
        ("ROA",         "roa",         "metrics",  fmt_pct,   "ROA",         "small"),
        ("Gross Margin","gross_margin","metrics",  fmt_pct,   "GROSS MARGIN","small"),
        ("Net Margin",  "net_margin",  "metrics",  fmt_pct,   "NET MARGIN",  "small"),
        ("Rev Growth",  "revenue_growth","metrics",fmt_pct,   "REV GROWTH",  "small"),
    ]),
    ("📝 My Notes", [
        ("Buy Target",  "target_buy",  "user",     fmt_str,   "BUY TARGET 🎯","small"),
        ("Sell Target", "target_sell", "user",     fmt_str,   "SELL TARGET 🎯","small"),
        ("Price Tag",   "price_tag",   "user",     fmt_str,   "PRICE TAG 🏷️","small"),
        ("Tag %",       "price_tag_pct","user",    fmt_str,   "TAG % 📊",    "small"),
        ("Sentiment",   "sentiment",   "user",     fmt_str,   "SENTIMENT 🧭","medium"),
        ("Comments",    "comments",    "user",     fmt_str,   "COMMENTS 📝", "large"),
    ]),
]

# Flat lookup: col_label → (db_key, api_source, fmt_fn, header, width)
COL_REGISTRY = {
    col: (db_key, src, fn, hdr, w)
    for _, grp in COLUMN_GROUPS
    for col, db_key, src, fn, hdr, w in grp
}

MARKET_FIELDS = [
    "name","sector","industry","price","change_pct","market_cap",
    "pe_ratio","week52_high","week52_low","week52_return",
    "beta","pb_ratio","ps_ratio","dividend_yield",
    "roe","roa","debt_equity","current_ratio",
    "gross_margin","net_margin","revenue_growth",
]
USER_FIELDS = ["target_buy","target_sell","price_tag","price_tag_pct","sentiment","comments"]

# ── Sidebar: Column Selector ──────────────────────────────────────────────────
st.sidebar.markdown("## ◈ STOCKPAD")
st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 Columns")
st.sidebar.caption("Price is always shown. Toggle others:")

# Default: all market columns ON, all user columns ON
if "selected_cols" not in st.session_state:
    st.session_state.selected_cols = {
        col: True
        for _, grp in COLUMN_GROUPS
        for col, *_ in grp
    }

selected_cols = st.session_state.selected_cols

for group_label, group_cols in COLUMN_GROUPS:
    st.sidebar.markdown(f"**{group_label}**")
    # Group select-all toggle
    all_on = all(selected_cols.get(col, True) for col, *_ in group_cols)
    grp_key = f"grp_{group_label}"
    if st.sidebar.checkbox(f"All {group_label.split(' ',1)[1]}", value=all_on, key=grp_key):
        for col, *_ in group_cols:
            selected_cols[col] = True
    else:
        for col, *_ in group_cols:
            selected_cols[col] = False
    # Individual checkboxes
    for col, db_key, src, fn, hdr, w in group_cols:
        selected_cols[col] = st.sidebar.checkbox(
            col, value=selected_cols.get(col, True), key=f"col_{col}"
        )
    st.sidebar.markdown("")

# Which API sources are actually needed?
needed_sources = {"quote", "profile"}  # quote always needed for price validation; profile for name
for col, (db_key, src, fn, hdr, w) in COL_REGISTRY.items():
    if selected_cols.get(col) and src not in ("user","fixed"):
        needed_sources.add(src)

st.sidebar.markdown("---")
st.sidebar.caption(f"API calls per stock: {len(needed_sources - {'user','fixed'})}")

# ── Fetch function ─────────────────────────────────────────────────────────────
def fetch_market_data(ticker):
    try:
        t = ticker.upper()
        result = {}

        # 1. Quote (always — needed for price + validation) ───────────────────
        quote = finnhub_get("quote", {"symbol": t})
        price = quote.get("c")
        prev  = quote.get("pc")
        if not price or price == 0:
            st.error(f"Ticker **{t}** not found on Finnhub.")
            return None
        result["price"]      = round(float(price), 2)
        result["change_pct"] = round(((price - prev) / prev) * 100, 2) if prev else None

        # 2. Profile (always — needed for name) ───────────────────────────────
        profile  = finnhub_get("stock/profile2", {"symbol": t})
        result["name"]       = profile.get("name") or t
        result["industry"]   = profile.get("finnhubIndustry") or "—"
        result["sector"]     = profile.get("ggroup") or profile.get("gcategory") or "—"
        result["market_cap"] = fmt_cap((profile.get("marketCapitalization") or 0) * 1_000_000) or None

        # 3. Metrics (only if any metrics column is selected) ─────────────────
        if "metrics" in needed_sources:
            metrics_resp = finnhub_get("stock/metric", {"symbol": t, "metric": "all"})
            m = metrics_resp.get("metric", {})
            def safe(key, fallbacks=None):
                v = m.get(key)
                if v is None and fallbacks:
                    for k in fallbacks:
                        v = m.get(k)
                        if v is not None: break
                return round(float(v), 4) if v is not None else None

            result["pe_ratio"]      = safe("peBasicExclExtraTTM", ["peTTM"])
            result["pb_ratio"]      = safe("pbAnnual", ["pbQuarterly"])
            result["ps_ratio"]      = safe("psAnnual", ["psTTM"])
            result["week52_high"]   = safe("52WeekHigh")
            result["week52_low"]    = safe("52WeekLow")
            result["week52_return"] = safe("52WeekPriceReturnDaily")
            result["beta"]          = safe("beta")
            result["debt_equity"]   = safe("totalDebt/totalEquityAnnual", ["totalDebt/totalEquityQuarterly"])
            result["current_ratio"] = safe("currentRatioAnnual", ["currentRatioQuarterly"])
            result["dividend_yield"]= safe("dividendYieldIndicatedAnnual")
            result["roe"]           = safe("roeTTM", ["roeRfy"])
            result["roa"]           = safe("roaTTM", ["roaRfy"])
            result["gross_margin"]  = safe("grossMarginTTM", ["grossMarginAnnual"])
            result["net_margin"]    = safe("netProfitMarginTTM", ["netProfitMarginAnnual"])
            result["revenue_growth"]= safe("revenueGrowthTTMYoy", ["revenueGrowth3Y"])

        return result

    except requests.exceptions.HTTPError as e:
        st.error(f"Finnhub API error for **{ticker}**: {e}")
        return None
    except Exception as e:
        st.error(f"Error fetching **{ticker}**: {e}")
        return None

# ── Supabase CRUD ─────────────────────────────────────────────────────────────
def db_load():
    return supabase.table("watchlist").select("*").order("created_at").execute().data or []

def db_insert(ticker, market):
    allowed = set(MARKET_FIELDS)
    clean   = {k: v for k, v in market.items() if k in allowed}
    row     = {"ticker": ticker.upper(), **clean, **{f: "" for f in USER_FIELDS}}
    return supabase.table("watchlist").insert(row).execute().data[0]

def db_update_market(ticker, market):
    allowed = set(MARKET_FIELDS)
    clean   = {k: v for k, v in market.items() if k in allowed}
    supabase.table("watchlist").update(clean).eq("ticker", ticker).execute()

def db_update_user_fields(ticker, fields):
    supabase.table("watchlist").update(fields).eq("ticker", ticker).execute()

def db_delete(ticker):
    supabase.table("watchlist").delete().eq("ticker", ticker).execute()

# ── Session state ─────────────────────────────────────────────────────────────
if "watchlist" not in st.session_state:
    st.session_state.watchlist = {r["ticker"]: r for r in db_load()}
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = None

wl = st.session_state.watchlist

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<div><div class="sp-logo"><span>◈</span> STOCKPAD</div><div class="sp-sub">LIGHTWEIGHT STOCK TRACKER · FINNHUB + SUPABASE</div></div>', unsafe_allow_html=True)
st.markdown("---")

total   = len(wl)
gainers = sum(1 for r in wl.values() if (r.get("change_pct") or 0) > 0)
losers  = sum(1 for r in wl.values() if (r.get("change_pct") or 0) < 0)

c1, c2, c3, c4 = st.columns([1,1,1,2])
with c1: st.metric("📊 Tracked", total)
with c2: st.metric("🟢 Gainers", gainers)
with c3: st.metric("🔴 Losers",  losers)
with c4: st.caption(f"Last refresh: {st.session_state.last_refresh or '—'}")

st.divider()

# ── Toolbar ───────────────────────────────────────────────────────────────────
col_inp, col_add, col_ref, _ = st.columns([2,1,1,4])
with col_inp:
    new_ticker = st.text_input("", placeholder="Enter ticker e.g. AAPL",
                               label_visibility="collapsed", key="ticker_input")
with col_add:
    add_clicked = st.button("＋ Add Stock", use_container_width=True, type="primary")
with col_ref:
    refresh_clicked = st.button("↻ Refresh All", use_container_width=True)

if add_clicked and new_ticker:
    t = new_ticker.strip().upper()
    if t in wl:
        st.warning(f"{t} is already in your watchlist.")
    else:
        with st.spinner(f"Fetching {t} from Finnhub..."):
            market = fetch_market_data(t)
        if market:
            row = db_insert(t, market)
            wl[t] = row
            st.session_state.last_refresh = datetime.now().strftime("%H:%M:%S")
            st.success(f"✓ {t} — {market['name']} added!")
            st.rerun()

if refresh_clicked and wl:
    with st.spinner("Refreshing all..."):
        for t in list(wl.keys()):
            market = fetch_market_data(t)
            if market:
                db_update_market(t, market)
                wl[t].update(market)
    st.session_state.last_refresh = datetime.now().strftime("%H:%M:%S")
    st.success("✓ All prices refreshed")
    st.rerun()

st.divider()

# ── Build active column list (always: Ticker + Price, then selected) ──────────
ALWAYS_COLS = ["Ticker", "Price"]   # mandatory, never toggled off
active_market_cols = [
    col for col, (db_key, src, fn, hdr, w) in COL_REGISTRY.items()
    if src != "user" and selected_cols.get(col, True)
]
active_user_cols = [
    col for col, (db_key, src, fn, hdr, w) in COL_REGISTRY.items()
    if src == "user" and selected_cols.get(col, True)
]
all_active_cols = ALWAYS_COLS + [c for c in active_market_cols if c not in ALWAYS_COLS] + active_user_cols

# ── Main table ────────────────────────────────────────────────────────────────
if not wl:
    st.markdown('<div style="text-align:center;padding:80px 20px;color:#2d3148;"><div style="font-size:48px;margin-bottom:16px;">◈</div><div style="font-size:14px;letter-spacing:3px;">ADD YOUR FIRST STOCK ABOVE</div></div>', unsafe_allow_html=True)
else:
    # Build raw df for sort/filter (numeric values)
    raw_rows = []
    for t, r in wl.items():
        row = {"Ticker": r["ticker"], "_price": r.get("price"), "_change_pct": r.get("change_pct")}
        for col, (db_key, src, fn, hdr, w) in COL_REGISTRY.items():
            row[f"_{db_key}"] = r.get(db_key)
        # user fields without underscore prefix (for editing)
        for col, (db_key, src, fn, hdr, w) in COL_REGISTRY.items():
            if src == "user":
                row[col] = r.get(db_key) or ""
        raw_rows.append(row)
    raw_df = pd.DataFrame(raw_rows)

    # ── Sort & Filter expander ────────────────────────────────────────────────
    with st.expander("🔍 Sort & Filter", expanded=False):
        fc1, fc2, fc3 = st.columns(3)
        fc4, fc5, fc6 = st.columns(3)

        with fc1:
            f_ticker = st.text_input("Ticker contains", key="f_ticker", placeholder="e.g. AA").upper()
        with fc2:
            industries = ["All"] + sorted(set(r.get("industry") or "—" for r in wl.values()))
            f_industry = st.selectbox("Industry", industries, key="f_industry")
        with fc3:
            f_sentiment = st.selectbox("Sentiment", ["All"] + [s for s in SENTIMENTS if s], key="f_sent")
        with fc4:
            f_chg_min, f_chg_max = st.slider("% Change range", -20.0, 20.0, (-20.0, 20.0), 0.5, key="f_chg")
        with fc5:
            sort_opts = {
                "Default (add order)": None,
                "Ticker A→Z": ("Ticker", True),
                "Price ↑": ("_price", True), "Price ↓": ("_price", False),
                "% Change ↑": ("_change_pct", True), "% Change ↓": ("_change_pct", False),
                "P/E ↑": ("_pe_ratio", True), "P/E ↓": ("_pe_ratio", False),
                "52W Return ↑": ("_week52_return", True), "52W Return ↓": ("_week52_return", False),
                "Beta ↑": ("_beta", True), "Beta ↓": ("_beta", False),
                "ROE ↑": ("_roe", True), "ROE ↓": ("_roe", False),
                "Net Margin ↑": ("_net_margin", True), "Net Margin ↓": ("_net_margin", False),
                "Rev Growth ↑": ("_revenue_growth", True), "Rev Growth ↓": ("_revenue_growth", False),
                "Div Yield ↑": ("_dividend_yield", True), "Div Yield ↓": ("_dividend_yield", False),
            }
            sort_choice = st.selectbox("Sort by", list(sort_opts.keys()), key="f_sort")
        with fc6:
            f_gainers = st.checkbox("Gainers only 🟢", key="f_gain")
            f_losers  = st.checkbox("Losers only 🔴",  key="f_loss")

    # Apply filters
    mask = pd.Series([True] * len(raw_df), index=raw_df.index)
    if f_ticker:    mask &= raw_df["Ticker"].str.contains(f_ticker, case=False, na=False)
    if f_industry != "All": mask &= raw_df["_industry"].fillna("—") == f_industry
    if f_sentiment != "All": mask &= raw_df["Sentiment"].fillna("") == f_sentiment
    if f_gainers:   mask &= raw_df["_change_pct"].fillna(0) > 0
    if f_losers:    mask &= raw_df["_change_pct"].fillna(0) < 0
    mask &= raw_df["_change_pct"].fillna(0).between(f_chg_min, f_chg_max)
    filtered = raw_df[mask].copy()

    # Apply sort
    sv = sort_opts[sort_choice]
    if sv:
        filtered = filtered.sort_values(by=sv[0], ascending=sv[1], na_position="last")

    # Build display df with only active columns, formatted
    display_rows = []
    for _, r in filtered.iterrows():
        dr = {"Ticker": r["Ticker"], "Price": fmt_price(r["_price"])}
        for col in active_market_cols:
            if col in ("Ticker", "Price"): continue
            db_key, src, fn, hdr, w = COL_REGISTRY[col]
            dr[col] = fn(r.get(f"_{db_key}"))
        for col in active_user_cols:
            dr[col] = r.get(col, "")
        display_rows.append(dr)

    display_df = pd.DataFrame(display_rows) if display_rows else pd.DataFrame(columns=all_active_cols)

    st.caption(f"Showing {len(display_df)} of {len(wl)} stocks  ·  {len(all_active_cols)} columns active")

    # Build column_config and DISABLED list dynamically
    user_col_set = {col for col, (_, src, *_) in COL_REGISTRY.items() if src == "user"}
    DISABLED = [c for c in display_df.columns if c not in user_col_set]

    col_cfg = {
        "Ticker": st.column_config.TextColumn("TICKER", width="small"),
        "Price":  st.column_config.TextColumn("PRICE",  width="small"),
    }
    for col in all_active_cols:
        if col in ("Ticker", "Price"): continue
        db_key, src, fn, hdr, w = COL_REGISTRY[col]
        if col == "Sentiment":
            col_cfg[col] = st.column_config.SelectboxColumn(hdr, width=w, options=SENTIMENTS)
        else:
            col_cfg[col] = st.column_config.TextColumn(hdr, width=w)

    edited_df = st.data_editor(
        display_df, use_container_width=True, hide_index=True,
        disabled=DISABLED, column_config=col_cfg,
        key="main_editor", num_rows="fixed",
    )

    # Save user edits
    for _, row in edited_df.iterrows():
        t = row["Ticker"]
        if t not in wl: continue
        existing = wl[t]
        changed = {}
        for col in active_user_cols:
            db_key, src, fn, hdr, w = COL_REGISTRY[col]
            new_val = str(row.get(col, "")) if row.get(col) else ""
            if new_val != (existing.get(db_key) or ""):
                changed[db_key] = new_val
        if changed:
            db_update_user_fields(t, changed)
            wl[t].update(changed)

    st.divider()
    st.markdown("##### Manage Stocks")
    all_tickers = list(wl.keys())
    del_cols = st.columns(min(len(all_tickers), 8))
    for i, t in enumerate(all_tickers):
        with del_cols[i % 8]:
            if st.button(f"✕ {t}", key=f"del_{t}"):
                db_delete(t)
                del wl[t]
                st.rerun()

    st.divider()
    csv = edited_df.to_csv(index=False)
    st.download_button("⬇ Export to CSV", data=csv,
                       file_name=f"stockpad_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                       mime="text/csv")

st.markdown('<div style="margin-top:40px;padding-top:12px;border-top:1px solid #1c2030;font-size:10px;color:#2d3148;letter-spacing:2px;text-align:center;">STOCKPAD v0.6 · STREAMLIT + FINNHUB + SUPABASE</div>', unsafe_allow_html=True)
