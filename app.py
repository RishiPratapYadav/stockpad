import streamlit as st
from supabase import create_client, Client
import yfinance as yf
import pandas as pd
from datetime import datetime

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="StockPad",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@600;700&display=swap');

html, body, [class*="css"] { font-family: 'IBM Plex Mono', monospace; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }

.sp-header {
    display: flex; align-items: flex-end; gap: 12px;
    border-bottom: 1px solid #1e2235;
    padding-bottom: 14px; margin-bottom: 20px;
}
.sp-logo {
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 26px; font-weight: 700; letter-spacing: 3px; color: #d8e0f0;
}
.sp-logo span { color: #3d7eff; }
.sp-sub { font-size: 10px; color: #3a4060; letter-spacing: 4px; margin-bottom: 3px; }
hr { border-color: #1c2030 !important; }
</style>
""", unsafe_allow_html=True)

# ── Supabase Client ───────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase() -> Client:
    url  = st.secrets["SUPABASE_URL"]
    key  = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = get_supabase()

# ── Constants ─────────────────────────────────────────────────────────────────
SENTIMENTS   = ["", "🟢 Bullish", "🔴 Bearish", "🟡 Neutral", "⚪ Watching"]
USER_FIELDS  = ["target_buy", "target_sell", "price_tag", "price_tag_pct", "sentiment", "comments"]
MARKET_FIELDS= ["name", "price", "change_pct", "pe_ratio", "week52_high", "week52_low", "market_cap"]

# ── Helpers ───────────────────────────────────────────────────────────────────

def fmt_price(v):
    if v is None: return "—"
    return f"${float(v):,.2f}"

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

def fetch_market_data(ticker: str) -> dict | None:
    try:
        info = yf.Ticker(ticker).info
        price      = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        if not price:
            return None
        chg = round(((price - prev_close) / prev_close) * 100, 2) if prev_close else None
        raw_cap = info.get("marketCap")
        return {
            "name":        info.get("shortName") or info.get("longName") or ticker.upper(),
            "price":       round(float(price), 2),
            "change_pct":  chg,
            "pe_ratio":    round(float(info["trailingPE"]), 2) if info.get("trailingPE") else None,
            "week52_high": round(float(info["fiftyTwoWeekHigh"]), 2) if info.get("fiftyTwoWeekHigh") else None,
            "week52_low":  round(float(info["fiftyTwoWeekLow"]), 2) if info.get("fiftyTwoWeekLow") else None,
            "market_cap":  fmt_cap(raw_cap),
        }
    except Exception as e:
        st.error(f"yfinance error: {e}")
        return None

# ── Supabase CRUD ─────────────────────────────────────────────────────────────

def db_load() -> list[dict]:
    res = supabase.table("watchlist").select("*").order("created_at").execute()
    return res.data or []

def db_insert(ticker: str, market: dict) -> dict:
    row = {
        "ticker":       ticker.upper(),
        **market,
        "target_buy":   "",
        "target_sell":  "",
        "price_tag":    "",
        "price_tag_pct":"",
        "sentiment":    "",
        "comments":     "",
    }
    res = supabase.table("watchlist").insert(row).execute()
    return res.data[0]

def db_update_market(ticker: str, market: dict):
    supabase.table("watchlist").update(market).eq("ticker", ticker).execute()

def db_update_user_fields(ticker: str, fields: dict):
    supabase.table("watchlist").update(fields).eq("ticker", ticker).execute()

def db_delete(ticker: str):
    supabase.table("watchlist").delete().eq("ticker", ticker).execute()

# ── Load data into session state ──────────────────────────────────────────────
if "watchlist" not in st.session_state:
    st.session_state.watchlist = {r["ticker"]: r for r in db_load()}

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = None

wl = st.session_state.watchlist

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="sp-header">
  <div>
    <div class="sp-logo"><span>◈</span> STOCKPAD</div>
    <div class="sp-sub">LIGHTWEIGHT STOCK TRACKER · POWERED BY SUPABASE</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Summary Metrics ───────────────────────────────────────────────────────────
total   = len(wl)
gainers = sum(1 for r in wl.values() if (r.get("change_pct") or 0) > 0)
losers  = sum(1 for r in wl.values() if (r.get("change_pct") or 0) < 0)

c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
with c1: st.metric("📊 Tracked", total)
with c2: st.metric("🟢 Gainers", gainers)
with c3: st.metric("🔴 Losers",  losers)
with c4: st.caption(f"Last refresh: {st.session_state.last_refresh or '—'}")

st.divider()

# ── Toolbar ───────────────────────────────────────────────────────────────────
col_inp, col_add, col_ref, col_gap = st.columns([2, 1, 1, 4])

with col_inp:
    new_ticker = st.text_input(
        "", placeholder="Enter ticker e.g. AAPL",
        label_visibility="collapsed", key="ticker_input"
    )
with col_add:
    add_clicked = st.button("＋ Add Stock", use_container_width=True, type="primary")
with col_ref:
    refresh_clicked = st.button("↻ Refresh All", use_container_width=True)

# ── Add Stock ─────────────────────────────────────────────────────────────────
if add_clicked and new_ticker:
    t = new_ticker.strip().upper()
    if t in wl:
        st.warning(f"{t} is already in your watchlist.")
    else:
        with st.spinner(f"Fetching {t} from Yahoo Finance..."):
            market = fetch_market_data(t)
        if market:
            row = db_insert(t, market)
            wl[t] = row
            st.session_state.last_refresh = datetime.now().strftime("%H:%M:%S")
            st.success(f"✓ {t} — {market['name']} added and saved!")
            st.rerun()
        else:
            st.error(f"Ticker '{t}' not found. Check the symbol and try again.")

# ── Refresh All ───────────────────────────────────────────────────────────────
if refresh_clicked and wl:
    with st.spinner("Refreshing all prices..."):
        for t in list(wl.keys()):
            market = fetch_market_data(t)
            if market:
                db_update_market(t, market)
                wl[t].update(market)
    st.session_state.last_refresh = datetime.now().strftime("%H:%M:%S")
    st.success("✓ All prices refreshed and saved to Supabase")
    st.rerun()

st.divider()

# ── Main Table ────────────────────────────────────────────────────────────────
if not wl:
    st.markdown("""
    <div style="text-align:center; padding:80px 20px; color:#2d3148;">
        <div style="font-size:48px; margin-bottom:16px;">◈</div>
        <div style="font-size:14px; letter-spacing:3px;">ADD YOUR FIRST STOCK ABOVE</div>
        <div style="font-size:11px; margin-top:8px; color:#1e2235; letter-spacing:2px;">TYPE A TICKER AND CLICK ADD STOCK</div>
    </div>
    """, unsafe_allow_html=True)
else:
    tickers = list(wl.keys())

    rows = []
    for t in tickers:
        r = wl[t]
        rows.append({
            "Ticker":      r["ticker"],
            "Name":        r.get("name") or "—",
            "Price":       fmt_price(r.get("price")),
            "% Chg":       fmt_pct(r.get("change_pct")),
            "P/E":         f"{r['pe_ratio']}x" if r.get("pe_ratio") else "—",
            "52W High":    fmt_price(r.get("week52_high")),
            "52W Low":     fmt_price(r.get("week52_low")),
            "Mkt Cap":     r.get("market_cap") or "—",
            "Buy Target":  r.get("target_buy")   or "",
            "Sell Target": r.get("target_sell")  or "",
            "Price Tag":   r.get("price_tag")    or "",
            "Tag %":       r.get("price_tag_pct")or "",
            "Sentiment":   r.get("sentiment")    or "",
            "Comments":    r.get("comments")     or "",
        })

    df = pd.DataFrame(rows)

    edited_df = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        disabled=["Ticker","Name","Price","% Chg","P/E","52W High","52W Low","Mkt Cap"],
        column_config={
            "Ticker":      st.column_config.TextColumn("TICKER",      width="small"),
            "Name":        st.column_config.TextColumn("NAME",        width="medium"),
            "Price":       st.column_config.TextColumn("PRICE",       width="small"),
            "% Chg":       st.column_config.TextColumn("% CHG",       width="small"),
            "P/E":         st.column_config.TextColumn("P/E",         width="small"),
            "52W High":    st.column_config.TextColumn("52W HIGH",     width="small"),
            "52W Low":     st.column_config.TextColumn("52W LOW",      width="small"),
            "Mkt Cap":     st.column_config.TextColumn("MKT CAP",     width="small"),
            "Buy Target":  st.column_config.TextColumn("BUY TARGET 🎯",  width="small"),
            "Sell Target": st.column_config.TextColumn("SELL TARGET 🎯", width="small"),
            "Price Tag":   st.column_config.TextColumn("PRICE TAG 🏷️",  width="small"),
            "Tag %":       st.column_config.TextColumn("TAG % 📊",       width="small"),
            "Sentiment":   st.column_config.SelectboxColumn(
                               "SENTIMENT 🧭", width="medium", options=SENTIMENTS),
            "Comments":    st.column_config.TextColumn("COMMENTS 📝",    width="large"),
        },
        key="main_editor",
        num_rows="fixed",
    )

    # ── Detect and save edits ─────────────────────────────────────────────────
    for i, t in enumerate(tickers):
        row      = edited_df.iloc[i]
        existing = wl[t]
        changed  = {}
        for field, col in [
            ("target_buy","Buy Target"), ("target_sell","Sell Target"),
            ("price_tag","Price Tag"),   ("price_tag_pct","Tag %"),
            ("sentiment","Sentiment"),   ("comments","Comments"),
        ]:
            new_val = str(row[col]) if row[col] else ""
            if new_val != (existing.get(field) or ""):
                changed[field] = new_val
        if changed:
            db_update_user_fields(t, changed)
            wl[t].update(changed)

    st.divider()

    # ── Delete buttons ────────────────────────────────────────────────────────
    st.markdown("##### Manage Stocks")
    cols = st.columns(min(len(tickers), 8))
    for i, t in enumerate(tickers):
        with cols[i % 8]:
            if st.button(f"✕ {t}", key=f"del_{t}", help=f"Remove {t}"):
                db_delete(t)
                del wl[t]
                st.rerun()

    st.divider()

    # ── Export CSV ────────────────────────────────────────────────────────────
    csv = edited_df.to_csv(index=False)
    st.download_button(
        label="⬇ Export to CSV",
        data=csv,
        file_name=f"stockpad_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-top:40px; padding-top:12px; border-top:1px solid #1c2030;
     font-size:10px; color:#2d3148; letter-spacing:2px; text-align:center;">
  STOCKPAD v0.2 · STREAMLIT + YFINANCE + SUPABASE · DATA PERSISTS ACROSS SESSIONS
</div>
""", unsafe_allow_html=True)
