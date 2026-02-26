import streamlit as st
from supabase import create_client, Client
import pandas as pd
import requests
from datetime import datetime

st.set_page_config(page_title="StockPad", page_icon="◈", layout="wide", initial_sidebar_state="collapsed")

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
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = get_supabase()

FINNHUB_KEY  = st.secrets["FINNHUB_KEY"]
FINNHUB_BASE = "https://finnhub.io/api/v1"

def finnhub_get(endpoint, params):
    params["token"] = FINNHUB_KEY
    r = requests.get(f"{FINNHUB_BASE}/{endpoint}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()

SENTIMENTS = ["", "🟢 Bullish", "🔴 Bearish", "🟡 Neutral", "⚪ Watching"]

MARKET_FIELDS = [
    "name","sector","industry","price","change_pct","market_cap",
    "pe_ratio","week52_high","week52_low","week52_return",
    "beta","pb_ratio","ps_ratio","dividend_yield",
    "roe","roa","debt_equity","current_ratio",
    "gross_margin","net_margin","revenue_growth",
]

USER_FIELDS = ["target_buy","target_sell","price_tag","price_tag_pct","sentiment","comments"]

def fmt_price(v):
    return f"${float(v):,.2f}" if v is not None else "—"

def fmt_cap(v):
    if not v: return "—"
    v = float(v)
    if v >= 1e12: return f"${v/1e12:.2f}T"
    if v >= 1e9:  return f"${v/1e9:.2f}B"
    if v >= 1e6:  return f"${v/1e6:.0f}M"
    return str(v)

def fmt_pct(v, d=2):
    if v is None: return "—"
    sign = "+" if float(v) >= 0 else ""
    return f"{sign}{float(v):.{d}f}%"

def fmt_x(v):
    return f"{float(v):.2f}x" if v is not None else "—"

def fmt_num(v):
    return f"{float(v):.2f}" if v is not None else "—"

def fetch_market_data(ticker):
    try:
        t = ticker.upper()

        quote = finnhub_get("quote", {"symbol": t})
        price = quote.get("c")
        prev  = quote.get("pc")
        if not price or price == 0:
            st.error(f"Ticker **{t}** not found on Finnhub.")
            return None
        chg = round(((price - prev) / prev) * 100, 2) if prev else None

        profile = finnhub_get("stock/profile2", {"symbol": t})
        name     = profile.get("name") or t
        sector   = profile.get("gsector") or profile.get("sector") or "—"
        industry = profile.get("finnhubIndustry") or profile.get("industry") or "—"
        mktcap   = profile.get("marketCapitalization")

        metrics_resp = finnhub_get("stock/metric", {"symbol": t, "metric": "all"})
        m = metrics_resp.get("metric", {})

        def safe(key, fallbacks=None):
            v = m.get(key)
            if v is None and fallbacks:
                for k in fallbacks:
                    v = m.get(k)
                    if v is not None: break
            return round(float(v), 4) if v is not None else None

        return {
            "name":          name,
            "sector":        sector,
            "industry":      industry,
            "price":         round(float(price), 2),
            "change_pct":    chg,
            "market_cap":    fmt_cap(mktcap * 1_000_000) if mktcap else None,
            "pe_ratio":      safe("peBasicExclExtraTTM", ["peTTM"]),
            "week52_high":   safe("52WeekHigh"),
            "week52_low":    safe("52WeekLow"),
            "week52_return": safe("52WeekPriceReturnDaily"),
            "beta":          safe("beta"),
            "pb_ratio":      safe("pbAnnual", ["pbQuarterly"]),
            "ps_ratio":      safe("psAnnual", ["psTTM"]),
            "dividend_yield":safe("dividendYieldIndicatedAnnual"),
            "roe":           safe("roeTTM", ["roeRfy"]),
            "roa":           safe("roaTTM", ["roaRfy"]),
            "debt_equity":   safe("totalDebt/totalEquityAnnual", ["totalDebt/totalEquityQuarterly"]),
            "current_ratio": safe("currentRatioAnnual", ["currentRatioQuarterly"]),
            "gross_margin":  safe("grossMarginTTM", ["grossMarginAnnual"]),
            "net_margin":    safe("netProfitMarginTTM", ["netProfitMarginAnnual"]),
            "revenue_growth":safe("revenueGrowthTTMYoy", ["revenueGrowth3Y"]),
        }
    except requests.exceptions.HTTPError as e:
        st.error(f"Finnhub API error for **{ticker}**: {e}")
        return None
    except Exception as e:
        st.error(f"Error fetching **{ticker}**: {e}")
        return None

def db_load():
    res = supabase.table("watchlist").select("*").order("created_at").execute()
    return res.data or []

def db_insert(ticker, market):
    allowed = set(MARKET_FIELDS)
    clean_market = {k: v for k, v in market.items() if k in allowed}
    row = {"ticker": ticker.upper(), **clean_market, **{f: "" for f in USER_FIELDS}}
    return supabase.table("watchlist").insert(row).execute().data[0]

def db_update_market(ticker, market):
    # Only send fields that are actual Supabase columns
    # and strip out any None → use None explicitly (not missing key)
    allowed = set(MARKET_FIELDS)
    clean = {k: v for k, v in market.items() if k in allowed}
    supabase.table("watchlist").update(clean).eq("ticker", ticker).execute()

def db_update_user_fields(ticker, fields):
    supabase.table("watchlist").update(fields).eq("ticker", ticker).execute()

def db_delete(ticker):
    supabase.table("watchlist").delete().eq("ticker", ticker).execute()

if "watchlist" not in st.session_state:
    st.session_state.watchlist = {r["ticker"]: r for r in db_load()}
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = None

wl = st.session_state.watchlist

st.markdown('<div><div class="sp-logo"><span>◈</span> STOCKPAD</div><div class="sp-sub">LIGHTWEIGHT STOCK TRACKER · FINNHUB + SUPABASE</div></div>', unsafe_allow_html=True)
st.markdown("---")

total   = len(wl)
gainers = sum(1 for r in wl.values() if (r.get("change_pct") or 0) > 0)
losers  = sum(1 for r in wl.values() if (r.get("change_pct") or 0) < 0)

c1,c2,c3,c4 = st.columns([1,1,1,2])
with c1: st.metric("📊 Tracked", total)
with c2: st.metric("🟢 Gainers", gainers)
with c3: st.metric("🔴 Losers",  losers)
with c4: st.caption(f"Last refresh: {st.session_state.last_refresh or '—'}")

st.divider()

col_inp, col_add, col_ref, _ = st.columns([2,1,1,4])
with col_inp:
    new_ticker = st.text_input("", placeholder="Enter ticker e.g. AAPL", label_visibility="collapsed", key="ticker_input")
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

if not wl:
    st.markdown('<div style="text-align:center;padding:80px 20px;color:#2d3148;"><div style="font-size:48px;margin-bottom:16px;">◈</div><div style="font-size:14px;letter-spacing:3px;">ADD YOUR FIRST STOCK ABOVE</div></div>', unsafe_allow_html=True)
else:
    # ── Build raw numeric dataframe (for sort/filter) ─────────────────────────
    raw_rows = []
    for t, r in wl.items():
        raw_rows.append({
            "_ticker":        r["ticker"],
            "Ticker":         r["ticker"],
            "Name":           r.get("name") or "—",
            "Sector":         r.get("sector") or "—",
            "Industry":       r.get("industry") or "—",
            # numeric cols (raw) for sort/filter
            "_price":         r.get("price"),
            "_change_pct":    r.get("change_pct"),
            "_pe":            r.get("pe_ratio"),
            "_pb":            r.get("pb_ratio"),
            "_ps":            r.get("ps_ratio"),
            "_52wh":          r.get("week52_high"),
            "_52wl":          r.get("week52_low"),
            "_52wr":          r.get("week52_return"),
            "_beta":          r.get("beta"),
            "_de":            r.get("debt_equity"),
            "_cr":            r.get("current_ratio"),
            "_dy":            r.get("dividend_yield"),
            "_roe":           r.get("roe"),
            "_roa":           r.get("roa"),
            "_gm":            r.get("gross_margin"),
            "_nm":            r.get("net_margin"),
            "_rg":            r.get("revenue_growth"),
            # user fields
            "Buy Target":     r.get("target_buy")    or "",
            "Sell Target":    r.get("target_sell")   or "",
            "Price Tag":      r.get("price_tag")     or "",
            "Tag %":          r.get("price_tag_pct") or "",
            "Sentiment":      r.get("sentiment")     or "",
            "Comments":       r.get("comments")      or "",
        })

    raw_df = pd.DataFrame(raw_rows)

    # ── Sort & Filter Controls ────────────────────────────────────────────────
    with st.expander("🔍 Sort & Filter", expanded=False):
        fc1, fc2, fc3 = st.columns(3)
        fc4, fc5, fc6 = st.columns(3)

        # Text filters
        with fc1:
            f_ticker = st.text_input("Ticker contains", key="f_ticker", placeholder="e.g. AA").upper()
        with fc2:
            all_industries = ["All"] + sorted(raw_df["Industry"].dropna().unique().tolist())
            f_industry = st.selectbox("Industry", all_industries, key="f_industry")
        with fc3:
            all_sentiments = ["All"] + [s for s in SENTIMENTS if s]
            f_sentiment = st.selectbox("Sentiment", all_sentiments, key="f_sent")

        # Numeric filters
        with fc4:
            f_chg_min, f_chg_max = st.slider(
                "% Change range", min_value=-20.0, max_value=20.0,
                value=(-20.0, 20.0), step=0.5, key="f_chg"
            )
        with fc5:
            numeric_sort_cols = {
                "Default (add order)": None,
                "Ticker (A→Z)":       ("Ticker", True),
                "Price ↑":            ("_price", True),
                "Price ↓":            ("_price", False),
                "% Change ↑":         ("_change_pct", True),
                "% Change ↓":         ("_change_pct", False),
                "P/E ↑":              ("_pe", True),
                "P/E ↓":              ("_pe", False),
                "Mkt Cap ↑":          ("_price", True),
                "52W Return ↑":       ("_52wr", True),
                "52W Return ↓":       ("_52wr", False),
                "Beta ↑":             ("_beta", True),
                "Beta ↓":             ("_beta", False),
                "ROE ↑":              ("_roe", True),
                "ROE ↓":              ("_roe", False),
                "Net Margin ↑":       ("_nm", True),
                "Net Margin ↓":       ("_nm", False),
                "Rev Growth ↑":       ("_rg", True),
                "Rev Growth ↓":       ("_rg", False),
                "Div Yield ↑":        ("_dy", True),
                "Div Yield ↓":        ("_dy", False),
            }
            sort_choice = st.selectbox("Sort by", list(numeric_sort_cols.keys()), key="f_sort")
        with fc6:
            f_gainers_only = st.checkbox("Gainers only 🟢", key="f_gain")
            f_losers_only  = st.checkbox("Losers only 🔴",  key="f_loss")

    # ── Apply filters ─────────────────────────────────────────────────────────
    mask = pd.Series([True] * len(raw_df), index=raw_df.index)

    if f_ticker:
        mask &= raw_df["Ticker"].str.contains(f_ticker, case=False, na=False)
    if f_industry != "All":
        mask &= raw_df["Industry"] == f_industry
    if f_sentiment != "All":
        mask &= raw_df["Sentiment"] == f_sentiment
    if f_gainers_only:
        mask &= raw_df["_change_pct"].fillna(0) > 0
    if f_losers_only:
        mask &= raw_df["_change_pct"].fillna(0) < 0

    # % change slider filter
    mask &= (
        raw_df["_change_pct"].fillna(0).between(f_chg_min, f_chg_max)
    )

    filtered_df = raw_df[mask].copy()

    # ── Apply sort ────────────────────────────────────────────────────────────
    sort_val = numeric_sort_cols[sort_choice]
    if sort_val:
        col_key, ascending = sort_val
        filtered_df = filtered_df.sort_values(
            by=col_key, ascending=ascending, na_position="last"
        )

    # ── Build display dataframe (formatted strings) ───────────────────────────
    display_rows = []
    for _, r in filtered_df.iterrows():
        display_rows.append({
            "Ticker":       r["Ticker"],
            "Name":         r["Name"],
            "Sector":       r["Sector"],
            "Industry":     r["Industry"],
            "Price":        fmt_price(r["_price"]),
            "% Chg":        fmt_pct(r["_change_pct"]),
            "P/E":          fmt_x(r["_pe"]),
            "P/B":          fmt_x(r["_pb"]),
            "P/S":          fmt_x(r["_ps"]),
            "52W High":     fmt_price(r["_52wh"]),
            "52W Low":      fmt_price(r["_52wl"]),
            "52W Return":   fmt_pct(r["_52wr"]),
            "Beta":         fmt_num(r["_beta"]),
            "Debt/Equity":  fmt_num(r["_de"]),
            "Curr Ratio":   fmt_num(r["_cr"]),
            "Div Yield":    fmt_pct(r["_dy"]),
            "ROE":          fmt_pct(r["_roe"]),
            "ROA":          fmt_pct(r["_roa"]),
            "Gross Margin": fmt_pct(r["_gm"]),
            "Net Margin":   fmt_pct(r["_nm"]),
            "Rev Growth":   fmt_pct(r["_rg"]),
            "Buy Target":   r["Buy Target"],
            "Sell Target":  r["Sell Target"],
            "Price Tag":    r["Price Tag"],
            "Tag %":        r["Tag %"],
            "Sentiment":    r["Sentiment"],
            "Comments":     r["Comments"],
        })

    display_df = pd.DataFrame(display_rows) if display_rows else pd.DataFrame(
        columns=["Ticker","Name","Sector","Industry","Price","% Chg",
                 "P/E","P/B","P/S","52W High","52W Low","52W Return",
                 "Beta","Debt/Equity","Curr Ratio","Div Yield",
                 "ROE","ROA","Gross Margin","Net Margin","Rev Growth",
                 "Buy Target","Sell Target","Price Tag","Tag %","Sentiment","Comments"]
    )

    # Show filtered count
    st.caption(f"Showing {len(display_df)} of {len(wl)} stocks")

    DISABLED = ["Ticker","Name","Sector","Industry","Price","% Chg",
                "P/E","P/B","P/S","52W High","52W Low","52W Return",
                "Beta","Debt/Equity","Curr Ratio","Div Yield",
                "ROE","ROA","Gross Margin","Net Margin","Rev Growth"]

    edited_df = st.data_editor(
        display_df, use_container_width=True, hide_index=True, disabled=DISABLED,
        column_config={
            "Ticker":       st.column_config.TextColumn("TICKER",        width="small"),
            "Name":         st.column_config.TextColumn("NAME",          width="medium"),
            "Sector":       st.column_config.TextColumn("SECTOR",        width="medium"),
            "Industry":     st.column_config.TextColumn("INDUSTRY",      width="medium"),
            "Price":        st.column_config.TextColumn("PRICE",         width="small"),
            "% Chg":        st.column_config.TextColumn("% CHG",         width="small"),
            "P/E":          st.column_config.TextColumn("P/E",           width="small"),
            "P/B":          st.column_config.TextColumn("P/B",           width="small"),
            "P/S":          st.column_config.TextColumn("P/S",           width="small"),
            "52W High":     st.column_config.TextColumn("52W HIGH",      width="small"),
            "52W Low":      st.column_config.TextColumn("52W LOW",       width="small"),
            "52W Return":   st.column_config.TextColumn("52W RETURN",    width="small"),
            "Beta":         st.column_config.TextColumn("BETA",          width="small"),
            "Debt/Equity":  st.column_config.TextColumn("DEBT/EQ",       width="small"),
            "Curr Ratio":   st.column_config.TextColumn("CURR RATIO",    width="small"),
            "Div Yield":    st.column_config.TextColumn("DIV YIELD",     width="small"),
            "ROE":          st.column_config.TextColumn("ROE",           width="small"),
            "ROA":          st.column_config.TextColumn("ROA",           width="small"),
            "Gross Margin": st.column_config.TextColumn("GROSS MARGIN",  width="small"),
            "Net Margin":   st.column_config.TextColumn("NET MARGIN",    width="small"),
            "Rev Growth":   st.column_config.TextColumn("REV GROWTH",    width="small"),
            "Buy Target":   st.column_config.TextColumn("BUY TARGET 🎯", width="small"),
            "Sell Target":  st.column_config.TextColumn("SELL TARGET 🎯",width="small"),
            "Price Tag":    st.column_config.TextColumn("PRICE TAG 🏷️",  width="small"),
            "Tag %":        st.column_config.TextColumn("TAG % 📊",      width="small"),
            "Sentiment":    st.column_config.SelectboxColumn("SENTIMENT 🧭", width="medium", options=SENTIMENTS),
            "Comments":     st.column_config.TextColumn("COMMENTS 📝",   width="large"),
        },
        key="main_editor", num_rows="fixed",
    )

    # ── Save user edits back to Supabase ──────────────────────────────────────
    # Map display rows back to tickers using Ticker column
    for i, row in edited_df.iterrows():
        t = row["Ticker"]
        if t not in wl:
            continue
        existing = wl[t]
        changed = {}
        for field, col in [("target_buy","Buy Target"),("target_sell","Sell Target"),
                           ("price_tag","Price Tag"),("price_tag_pct","Tag %"),
                           ("sentiment","Sentiment"),("comments","Comments")]:
            new_val = str(row[col]) if row[col] else ""
            if new_val != (existing.get(field) or ""):
                changed[field] = new_val
        if changed:
            db_update_user_fields(t, changed)
            wl[t].update(changed)

    st.divider()
    st.markdown("##### Manage Stocks")
    all_tickers = list(wl.keys())
    cols = st.columns(min(len(all_tickers), 8))
    for i, t in enumerate(all_tickers):
        with cols[i % 8]:
            if st.button(f"✕ {t}", key=f"del_{t}"):
                db_delete(t)
                del wl[t]
                st.rerun()

    st.divider()
    csv = edited_df.to_csv(index=False)
    st.download_button("⬇ Export to CSV", data=csv,
                       file_name=f"stockpad_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                       mime="text/csv")

st.markdown('<div style="margin-top:40px;padding-top:12px;border-top:1px solid #1c2030;font-size:10px;color:#2d3148;letter-spacing:2px;text-align:center;">STOCKPAD v0.4 · STREAMLIT + FINNHUB + SUPABASE</div>', unsafe_allow_html=True)
