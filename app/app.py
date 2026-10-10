import base64
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

st.set_page_config(
    page_title="Stock Market Analysis",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -------------------- CHART THEME --------------------
# Colour order matters: 1st = sky blue, 2nd = amber (clear contrast for two-series charts),
# then violet / emerald / rose / fuchsia for the 6-stock charts and signal markers.
CHART_COLORWAY = ["#38bdf8", "#f59e0b", "#a78bfa", "#34d399", "#fb7185", "#e879f9"]
CHART_BG = "#0f1a2e"
CHART_GRID = "#1f3250"
CHART_TEXT = "#dbe7f5"
pio.templates["stock_dark"] = go.layout.Template(
    layout=go.Layout(
        colorway=CHART_COLORWAY,
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        font=dict(color=CHART_TEXT),
        title=dict(font=dict(size=18, color="#f1f6fd")),
        xaxis=dict(gridcolor=CHART_GRID, zerolinecolor="#2f4a73", linecolor="#2f4a73"),
        yaxis=dict(gridcolor=CHART_GRID, zerolinecolor="#2f4a73", linecolor="#2f4a73"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#16253d", bordercolor="#2f4a73", font=dict(color="#f1f6fd")),
    ),
    data=dict(bar=[go.Bar(marker=dict(line=dict(width=0)),
                          insidetextfont=dict(color="#0b1220"),
                          outsidetextfont=dict(color=CHART_TEXT))]),
)
pio.templates.default = "stock_dark"

def show_chart(fig):
    # theme=None so Streamlit does not override the custom chart colours/background
    st.plotly_chart(fig, use_container_width=True, theme=None)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT.parent / "data"
if not DATA_DIR.exists():
    DATA_DIR = ROOT

FILES = {
    "Bajaj Auto.csv": "bajaj_auto",
    "Eicher Motors.csv": "eicher_motors",
    "Hero Motocorp.csv": "hero_motocorp",
    "Infosys.csv": "infosys",
    "TCS.csv": "tcs",
    "TVS Motors.csv": "tvs_motors",
}
DISPLAY_TO_TABLE = {
    "Bajaj Auto": "bajaj_auto",
    "Eicher Motors": "eicher_motors",
    "Hero Motocorp": "hero_motocorp",
    "Infosys": "infosys",
    "TCS": "tcs",
    "TVS Motors": "tvs_motors",
}
COLS = {
    "Date": "date",
    "Open Price": "open_price",
    "High Price": "high_price",
    "Low Price": "low_price",
    "Close Price": "close_price",
    "WAP": "wap",
    "No.of Shares": "no_of_shares",
    "No. of Trades": "no_of_trades",
    "Total Turnover (Rs.)": "total_turnover",
    "Deliverable Quantity": "deliverable_qty",
    "% Deli. Qty to Traded Qty": "pct_deli_qty",
    "Spread High-Low": "spread_high_low",
    "Spread Close-Open": "spread_close_open",
}

@st.cache_resource
def build_db():
    con = sqlite3.connect(":memory:", check_same_thread=False)
    for filename, table in FILES.items():
        path = DATA_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing dataset: {path}")
        df = pd.read_csv(path).rename(columns=COLS)
        df["date"] = pd.to_datetime(
            df["date"], format="%d-%B-%Y"
        ).dt.strftime("%Y-%m-%d")
        for c in df.columns:
            if c != "date":
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.sort_values("date")
        df.to_sql(table, con, index=False, if_exists="replace")
        con.execute(f"CREATE INDEX idx_{table}_date ON {table}(date)")
    con.commit()
    return con

con = build_db()

STOCKS = list(DISPLAY_TO_TABLE)

def sql_df(query, params=()):
    return pd.read_sql_query(query, con, params=params)

def fmt_pct(x):
    return f"{x:+.1f}%"

def stock_union(adjusted=False):
    parts = []
    for display, table in DISPLAY_TO_TABLE.items():
        if adjusted and display == "TCS":
            close = "CASE WHEN date < '2018-05-31' THEN close_price/2.0 ELSE close_price END"
        elif adjusted and display == "Infosys":
            close = "CASE WHEN date < '2015-06-15' THEN close_price/2.0 ELSE close_price END"
        else:
            close = "close_price"
        parts.append(f"SELECT '{display}' stock, date, {close} close_price FROM {table}")
    return "\nUNION ALL\n".join(parts)

def return_table(adjusted=True):
    q = f"""
    WITH prices AS ({stock_union(adjusted)}),
    first_last AS (
        SELECT stock, MIN(date) first_date, MAX(date) last_date
        FROM prices GROUP BY stock
    )
    SELECT f.stock,
           p1.close_price first_close,
           p2.close_price last_close,
           ROUND(100.0*(p2.close_price/p1.close_price-1),1) return_pct
    FROM first_last f
    JOIN prices p1 ON p1.stock=f.stock AND p1.date=f.first_date
    JOIN prices p2 ON p2.stock=f.stock AND p2.date=f.last_date
    ORDER BY return_pct DESC
    """
    return sql_df(q)

def growth_series(adjusted=True):
    q = f"""
    WITH prices AS ({stock_union(adjusted)}),
    firsts AS (
        SELECT stock, MIN(date) first_date
        FROM prices GROUP BY stock
    ),
    base AS (
        SELECT p.stock, p.date, p.close_price,
               FIRST_VALUE(p.close_price) OVER (
                   PARTITION BY p.stock ORDER BY p.date
               ) first_close
        FROM prices p
    )
    SELECT stock,date,
           ROUND(100.0*close_price/first_close,2) growth_of_100
    FROM base
    ORDER BY date,stock
    """
    return sql_df(q)

def signal_data(stock):
    table = DISPLAY_TO_TABLE[stock]
    # Corporate-action adjustment is applied for TCS/Infosys before
    # moving averages so their signals are not distorted by the bonus event.
    if stock == "TCS":
        price_expr = "CASE WHEN date < '2018-05-31' THEN close_price/2.0 ELSE close_price END"
    elif stock == "Infosys":
        price_expr = "CASE WHEN date < '2015-06-15' THEN close_price/2.0 ELSE close_price END"
    else:
        price_expr = "close_price"
    q = f"""
    WITH prices AS (
        SELECT date, {price_expr} close_price
        FROM {table}
    ),
    ma AS (
        SELECT date,close_price,
               CASE WHEN ROW_NUMBER() OVER (ORDER BY date)>=20 THEN
                    AVG(close_price) OVER (
                        ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) END ma20,
               CASE WHEN ROW_NUMBER() OVER (ORDER BY date)>=50 THEN
                    AVG(close_price) OVER (
                        ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW
                    ) END ma50
        FROM prices
    ),
    lagged AS (
        SELECT *,
               LAG(ma20) OVER (ORDER BY date) prev_ma20,
               LAG(ma50) OVER (ORDER BY date) prev_ma50
        FROM ma
    )
    SELECT date,close_price,ROUND(ma20,2) ma20,ROUND(ma50,2) ma50,
           CASE
             WHEN ma20 > ma50 AND prev_ma20 <= prev_ma50 THEN 'Buy'
             WHEN ma20 < ma50 AND prev_ma20 >= prev_ma50 THEN 'Sell'
             ELSE 'Hold'
           END signal
    FROM lagged
    ORDER BY date
    """
    return sql_df(q)

def risk_metrics(stock):
    table = DISPLAY_TO_TABLE[stock]
    if stock == "TCS":
        expr = "CASE WHEN date < '2018-05-31' THEN close_price/2.0 ELSE close_price END"
    elif stock == "Infosys":
        expr = "CASE WHEN date < '2015-06-15' THEN close_price/2.0 ELSE close_price END"
    else:
        expr = "close_price"
    q = f"""
    WITH prices AS (
        SELECT date,{expr} close_price FROM {table}
    ),
    returns AS (
        SELECT date,close_price,
               close_price/LAG(close_price) OVER (ORDER BY date)-1 daily_return
        FROM prices
    ),
    running AS (
        SELECT *,
               MAX(close_price) OVER (
                   ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               ) peak
        FROM returns
    )
    SELECT
       COUNT(daily_return) return_days,
       AVG(daily_return) avg_daily,
       SQRT(AVG(daily_return*daily_return)-AVG(daily_return)*AVG(daily_return)) volatility,
       MIN(daily_return) worst_day,
       MAX(daily_return) best_day,
       SUM(CASE WHEN daily_return > 0 THEN 1 ELSE 0 END) up_days,
       SUM(CASE WHEN daily_return < 0 THEN 1 ELSE 0 END) down_days,
       MIN(close_price/peak-1) max_drawdown
    FROM running
    """
    return sql_df(q).iloc[0]

QUERIES = {
    "Data coverage": """SELECT 'Bajaj Auto' stock, COUNT(*) trading_days, MIN(date) first_day, MAX(date) last_day FROM bajaj_auto
UNION ALL SELECT 'Eicher Motors', COUNT(*), MIN(date), MAX(date) FROM eicher_motors
UNION ALL SELECT 'Hero Motocorp', COUNT(*), MIN(date), MAX(date) FROM hero_motocorp
UNION ALL SELECT 'Infosys', COUNT(*), MIN(date), MAX(date) FROM infosys
UNION ALL SELECT 'TCS', COUNT(*), MIN(date), MAX(date) FROM tcs
UNION ALL SELECT 'TVS Motors', COUNT(*), MIN(date), MAX(date) FROM tvs_motors;""",
    "Eicher top 5 closes": "SELECT date, close_price FROM eicher_motors ORDER BY close_price DESC LIMIT 5;",
    "TCS yearly average": "SELECT strftime('%Y',date) year, ROUND(AVG(close_price),2) avg_close FROM tcs GROUP BY 1 ORDER BY 1;",
    "Missing deliverables": """SELECT 'Bajaj Auto' stock,date FROM bajaj_auto WHERE deliverable_qty IS NULL
UNION ALL SELECT 'Eicher Motors',date FROM eicher_motors WHERE deliverable_qty IS NULL
UNION ALL SELECT 'Hero Motocorp',date FROM hero_motocorp WHERE deliverable_qty IS NULL
UNION ALL SELECT 'Infosys',date FROM infosys WHERE deliverable_qty IS NULL
UNION ALL SELECT 'TCS',date FROM tcs WHERE deliverable_qty IS NULL
UNION ALL SELECT 'TVS Motors',date FROM tvs_motors WHERE deliverable_qty IS NULL
ORDER BY date,stock;""",
    "Bajaj MA20/MA50": """WITH x AS (
SELECT date,close_price,
AVG(close_price) OVER(ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) ma20,
AVG(close_price) OVER(ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) ma50,
ROW_NUMBER() OVER(ORDER BY date) rn
FROM bajaj_auto)
SELECT date,close_price,
CASE WHEN rn>=20 THEN ROUND(ma20,2) END ma20,
CASE WHEN rn>=50 THEN ROUND(ma50,2) END ma50
FROM x ORDER BY date;""",
    "All-stock signals": """WITH prices AS (
SELECT 'Bajaj Auto' stock,date,close_price FROM bajaj_auto
UNION ALL SELECT 'Eicher Motors',date,close_price FROM eicher_motors
UNION ALL SELECT 'Hero Motocorp',date,close_price FROM hero_motocorp
UNION ALL SELECT 'Infosys',date,close_price FROM infosys
UNION ALL SELECT 'TCS',date,close_price FROM tcs
UNION ALL SELECT 'TVS Motors',date,close_price FROM tvs_motors),
ma AS (
SELECT stock,date,close_price,
AVG(close_price) OVER(PARTITION BY stock ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) ma20,
AVG(close_price) OVER(PARTITION BY stock ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) ma50,
ROW_NUMBER() OVER(PARTITION BY stock ORDER BY date) rn
FROM prices),
lagged AS (
SELECT *,LAG(ma20) OVER(PARTITION BY stock ORDER BY date) prev_ma20,
LAG(ma50) OVER(PARTITION BY stock ORDER BY date) prev_ma50 FROM ma)
SELECT stock,date,close_price,ROUND(ma20,2) ma20,ROUND(ma50,2) ma50,
CASE WHEN ma20>ma50 AND prev_ma20<=prev_ma50 THEN 'Buy'
WHEN ma20<ma50 AND prev_ma20>=prev_ma50 THEN 'Sell' ELSE 'Hold' END signal
FROM lagged ORDER BY stock,date;""",
    "Raw returns": """WITH prices AS (
SELECT 'Bajaj Auto' stock,date,close_price FROM bajaj_auto UNION ALL
SELECT 'Eicher Motors',date,close_price FROM eicher_motors UNION ALL
SELECT 'Hero Motocorp',date,close_price FROM hero_motocorp UNION ALL
SELECT 'Infosys',date,close_price FROM infosys UNION ALL
SELECT 'TCS',date,close_price FROM tcs UNION ALL
SELECT 'TVS Motors',date,close_price FROM tvs_motors),
e AS (SELECT stock,MIN(date) first_date,MAX(date) last_date FROM prices GROUP BY stock)
SELECT e.stock,p1.close_price first_close,p2.close_price last_close,
ROUND(100.0*(p2.close_price/p1.close_price-1),1) return_pct
FROM e JOIN prices p1 ON p1.stock=e.stock AND p1.date=e.first_date
JOIN prices p2 ON p2.stock=e.stock AND p2.date=e.last_date
ORDER BY return_pct DESC;""",
    "Worst daily move": """WITH prices AS (
SELECT 'Bajaj Auto' stock,date,close_price FROM bajaj_auto UNION ALL
SELECT 'Eicher Motors',date,close_price FROM eicher_motors UNION ALL
SELECT 'Hero Motocorp',date,close_price FROM hero_motocorp UNION ALL
SELECT 'Infosys',date,close_price FROM infosys UNION ALL
SELECT 'TCS',date,close_price FROM tcs UNION ALL
SELECT 'TVS Motors',date,close_price FROM tvs_motors),
m AS (SELECT stock,date,close_price,
100.0*(close_price/LAG(close_price) OVER(PARTITION BY stock ORDER BY date)-1) pct_move FROM prices),
r AS (SELECT *,ROW_NUMBER() OVER(PARTITION BY stock ORDER BY pct_move) rn FROM m WHERE pct_move IS NOT NULL)
SELECT stock,date,close_price,ROUND(pct_move,1) pct_move FROM r WHERE rn=1 ORDER BY pct_move;""",
    "Adjusted TCS/Infosys returns": """WITH adjusted AS (
SELECT 'TCS' stock,date,CASE WHEN date<'2018-05-31' THEN close_price/2.0 ELSE close_price END adj_close FROM tcs
UNION ALL SELECT 'Infosys',date,CASE WHEN date<'2015-06-15' THEN close_price/2.0 ELSE close_price END FROM infosys),
e AS (SELECT stock,MIN(date) first_date,MAX(date) last_date FROM adjusted GROUP BY stock)
SELECT e.stock,ROUND(100.0*(
MAX(CASE WHEN a.date=e.last_date THEN a.adj_close END)/
MAX(CASE WHEN a.date=e.first_date THEN a.adj_close END)-1),1) adjusted_return_pct
FROM e JOIN adjusted a ON a.stock=e.stock GROUP BY e.stock;""",
    "Risk metrics": """WITH prices AS (
SELECT 'Bajaj Auto' stock,date,close_price FROM bajaj_auto UNION ALL
SELECT 'Eicher Motors',date,close_price FROM eicher_motors UNION ALL
SELECT 'Hero Motocorp',date,close_price FROM hero_motocorp UNION ALL
SELECT 'Infosys',date,close_price FROM infosys UNION ALL
SELECT 'TCS',date,close_price FROM tcs UNION ALL
SELECT 'TVS Motors',date,close_price FROM tvs_motors),
r AS (SELECT stock,date,close_price,
close_price/LAG(close_price) OVER(PARTITION BY stock ORDER BY date)-1 daily_return FROM prices)
SELECT stock,COUNT(daily_return) return_days,
ROUND(100*AVG(daily_return),4) avg_daily_return_pct,
ROUND(100*SQRT(AVG(daily_return*daily_return)-AVG(daily_return)*AVG(daily_return)),2) volatility_pct,
ROUND(100*MIN(daily_return),2) worst_day_pct,
ROUND(100*MAX(daily_return),2) best_day_pct
FROM r GROUP BY stock ORDER BY stock;"""
}

# -------------------- NAVIGATION --------------------
st.markdown("""
<style>
:root { --bg:#0a1322; --panel:#0f1a2e; --panel2:#13213a; --border:#22385a; --accent:#38bdf8; --text:#e6edf7; --muted:#9db3d1; }
html, body, [data-testid="stAppViewContainer"], .stApp {
    background: linear-gradient(180deg,#0c1628 0%,#0a1322 55%,#08101d 100%) !important;
    color: var(--text) !important;
}
[data-testid="stHeader"] { background:rgba(10,19,34,.92) !important; }
[data-testid="stSidebar"] { background:linear-gradient(180deg,#0e1a2f 0%,#0b1527 100%) !important; border-right:1px solid #1d3253; }
[data-testid="stSidebar"] * { color:#d6e4f7 !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] label { padding:.35rem .2rem; }
.block-container { padding-top:1.1rem; padding-bottom:2rem; max-width:1600px; }
.ml-hero { display:flex; align-items:center; gap:1.2rem; background:linear-gradient(110deg,#0f1a2e 0%,#13284a 60%,#163e66 100%); padding:1.1rem 1.6rem; border:1px solid #24406a; border-left:4px solid var(--accent); border-radius:0 0 16px 16px; color:#f5f9ff; margin:0 0 1.1rem; box-shadow:0 12px 32px rgba(0,0,0,.28); }
.ml-logo-mark { width:68px; height:68px; object-fit:contain; flex-shrink:0; border-radius:16px; box-shadow:0 6px 18px rgba(56,189,248,.25); }
.ml-kicker { color:var(--accent); text-transform:uppercase; letter-spacing:.16em; font-size:.72rem; font-weight:800; }
.ml-title { color:#f4f8ff; font-size:2rem; font-weight:800; letter-spacing:-.03em; margin:.12rem 0; }
.ml-sub { color:var(--muted); margin:0; }
[data-testid="stAppViewContainer"] h1, [data-testid="stAppViewContainer"] h2, [data-testid="stAppViewContainer"] h3, [data-testid="stAppViewContainer"] h4 { color:#eff6ff !important; }
[data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] label, [data-testid="stCaptionContainer"] { color:var(--muted); }
div[data-testid="stMetric"] { background:linear-gradient(145deg,#13213a,#0f1a2e) !important; padding:1rem 1.1rem; border:1px solid var(--border); border-top:3px solid var(--accent); border-radius:14px; box-shadow:0 7px 20px rgba(0,0,0,.2); }
div[data-testid="stMetric"] label { color:var(--muted) !important; }
div[data-testid="stMetric"] [data-testid="stMetricValue"] { color:#f2f7ff !important; }
[data-testid="stPlotlyChart"] { background:var(--panel); border:1px solid var(--border); border-radius:14px; padding:.6rem .6rem .2rem; box-shadow:0 7px 20px rgba(0,0,0,.2); overflow:hidden; }
div[data-testid="stDataFrame"], div[data-testid="stTable"] { background:var(--panel) !important; border:1px solid var(--border); border-radius:12px; }
[data-testid="stDataFrame"] * { color:#e5efff !important; }
.stTabs [data-baseweb="tab-list"] { gap:.4rem; }
.stTabs [data-baseweb="tab"] { background:#13213a; color:#b9cde8; border:1px solid var(--border); border-radius:9px 9px 0 0; padding:.6rem 1rem; }
.stTabs [aria-selected="true"] { background:#1b3a63 !important; color:#ffffff !important; }
[data-baseweb="select"] > div, [data-baseweb="input"] > div, [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea { background:#13213a !important; color:#eff6ff !important; border-color:#2a4670 !important; }
[data-testid="stVerticalBlock"] [data-testid="stAlert"] { background:#13213a; }
hr { border-color:#22385a !important; }
</style>
""", unsafe_allow_html=True)

LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#38bdf8"/><stop offset="1" stop-color="#6366f1"/></linearGradient></defs>
<rect width="64" height="64" rx="14" fill="url(#g)"/>
<rect x="14" y="38" width="8" height="12" rx="2" fill="#ffffff" opacity=".85"/>
<rect x="28" y="28" width="8" height="22" rx="2" fill="#ffffff" opacity=".9"/>
<rect x="42" y="18" width="8" height="32" rx="2" fill="#ffffff"/>
<polyline points="12,34 26,24 36,30 52,11" fill="none" stroke="#fbbf24" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="52" cy="11" r="3.5" fill="#fbbf24"/>
</svg>"""
logo_data = "data:image/svg+xml;base64," + base64.b64encode(LOGO_SVG.encode("utf-8")).decode("ascii")
logo_html = f'<img class="ml-logo-mark" src="{logo_data}" alt="Stock Market Analysis logo">'
st.markdown(f'<div class="ml-hero">{logo_html}<div><div class="ml-kicker">Analyze · Visualize · Decide</div><div class="ml-title">Stock Market Analysis</div><p class="ml-sub">SQL-powered stock market analytics · Data → Insights</p></div></div>', unsafe_allow_html=True)

pages = ["📊 Overview", "🎯 Signal Explorer", "⚠️ Data Trap", "🛡️ Risk & Performance", "📈 Strategy vs Buy & Hold", "🧑‍💻 Live SQL Playground"]
with st.sidebar:
    st.markdown("### 📈 Stock Market Analysis")
    st.caption("SQL Powered Market Analytics")
    st.divider()
    page = st.radio("Navigate", pages, label_visibility="collapsed")
    st.divider()
    st.markdown("**Better data.**  \nSmarter analysis.  \nStronger decisions.")

if page == "📊 Overview":
    returns = return_table(adjusted=True)
    cov = sql_df("SELECT COUNT(*) n, MIN(date) first_day, MAX(date) last_day FROM bajaj_auto").iloc[0]
    cols = st.columns(4)
    cols[0].metric("Stocks", "6")
    cols[1].metric("Trading rows / stock", f"{int(cov.n):,}")
    cols[2].metric("Start", cov.first_day)
    cols[3].metric("End", cov.last_day)

    st.subheader("Market snapshot · adjusted full-period return")
    c1, c2 = st.columns([1.2, 1])
    with c1:
        fig = px.bar(returns, x="stock", y="return_pct", text="return_pct",
                     labels={"return_pct": "Return (%)", "stock": "Stock"},
                     title="Return by stock")
        fig.update_traces(texttemplate="%{text:+.1f}%", textposition="outside")
        show_chart(fig)
    with c2:
        st.dataframe(returns.rename(columns={
            "stock":"Stock","first_close":"First adjusted close",
            "last_close":"Last adjusted close","return_pct":"Return %"
        }), use_container_width=True, hide_index=True)

    st.subheader("Portfolio growth")
    selected = st.multiselect("Stocks", STOCKS, default=STOCKS)
    adjusted = st.toggle("Use bonus-adjusted prices for TCS/Infosys", value=True)
    growth = growth_series(adjusted)
    growth = growth[growth.stock.isin(selected)]
    fig = px.line(growth, x="date", y="growth_of_100", color="stock",
                  labels={"growth_of_100":"Value of ₹100", "date":"Date", "stock":"Stock"},
                  title="Growth of ₹100 from 1 Jan 2015")
    show_chart(fig)
    st.caption("Adjusted view divides pre-bonus TCS prices by 2 before 31 May 2018 and pre-bonus Infosys prices by 2 before 15 Jun 2015.")

elif page == "🎯 Signal Explorer":
    stock = st.selectbox("Select stock", STOCKS)
    df = signal_data(stock)
    nonhold = df[df.signal != "Hold"]
    counts = df.signal.value_counts()
    c = st.columns(4)
    c[0].metric("Buy signals", int(counts.get("Buy", 0)))
    c[1].metric("Sell signals", int(counts.get("Sell", 0)))
    c[2].metric("Hold days", int(counts.get("Hold", 0)))
    c[3].metric("Latest signal", str(nonhold.iloc[-1].signal) if not nonhold.empty else "—")

    st.subheader(f"{stock}: price and 20/50-day moving averages")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.date, y=df.close_price, name="Close", mode="lines"))
    fig.add_trace(go.Scatter(x=df.date, y=df.ma20, name="MA20", mode="lines"))
    fig.add_trace(go.Scatter(x=df.date, y=df.ma50, name="MA50", mode="lines"))
    buys = df[df.signal == "Buy"]
    sells = df[df.signal == "Sell"]
    fig.add_trace(go.Scatter(x=buys.date, y=buys.close_price, name="Buy", mode="markers",
                             marker=dict(symbol="triangle-up", size=10)))
    fig.add_trace(go.Scatter(x=sells.date, y=sells.close_price, name="Sell", mode="markers",
                             marker=dict(symbol="triangle-down", size=10)))
    fig.update_layout(hovermode="x unified", height=560, xaxis_title="Date", yaxis_title="Price")
    show_chart(fig)

    st.subheader("Signal history")
    show = df[df.signal != "Hold"].copy()
    show["close_price"] = show["close_price"].round(2)
    st.dataframe(show.tail(50), use_container_width=True, hide_index=True)

elif page == "⚠️ Data Trap":
    st.subheader("Data-quality and corporate-action diagnostics")
    missing = sql_df("""SELECT 'Bajaj Auto' stock,date FROM bajaj_auto WHERE deliverable_qty IS NULL
UNION ALL SELECT 'Eicher Motors',date FROM eicher_motors WHERE deliverable_qty IS NULL
UNION ALL SELECT 'Hero Motocorp',date FROM hero_motocorp WHERE deliverable_qty IS NULL
UNION ALL SELECT 'Infosys',date FROM infosys WHERE deliverable_qty IS NULL
UNION ALL SELECT 'TCS',date FROM tcs WHERE deliverable_qty IS NULL
UNION ALL SELECT 'TVS Motors',date FROM tvs_motors WHERE deliverable_qty IS NULL
ORDER BY date,stock""")
    worst = sql_df(QUERIES["Worst daily move"])
    c = st.columns(2)
    c[0].metric("Largest raw daily drop", f"{worst.pct_move.min():.1f}%")
    c[1].metric("Stocks investigated", 6)

    st.subheader("Worst raw daily movement by stock")
    st.dataframe(worst.rename(columns={"stock":"Stock","date":"Date","close_price":"Close","pct_move":"Daily move %"}),
                 use_container_width=True, hide_index=True)

    st.subheader("Raw vs corporate-action-adjusted return")
    raw = return_table(adjusted=False)[["stock","return_pct"]].rename(columns={"return_pct":"raw_return"})
    adj = return_table(adjusted=True)[["stock","return_pct"]].rename(columns={"return_pct":"adjusted_return"})
    compare = raw.merge(adj, on="stock")
    compare = compare[compare.stock.isin(["TCS","Infosys"])]
    long = compare.melt(id_vars="stock", var_name="basis", value_name="return_pct")
    long["basis"] = long["basis"].str.replace("_"," ").str.title()
    fig = px.bar(long, x="stock", y="return_pct", color="basis", barmode="group",
                 title="Corporate-action impact on full-period return",
                 labels={"return_pct":"Return (%)","stock":"Stock"})
    show_chart(fig)
    st.dataframe(compare, use_container_width=True, hide_index=True)

    st.info("TCS has a 1:1 bonus effective 31 May 2018; Infosys has a 1:1 bonus effective 15 Jun 2015. The dashboard uses the adjusted series when the adjusted view is selected.")

    st.subheader("Missing-value records")
    st.dataframe(missing, use_container_width=True, hide_index=True)

elif page == "🛡️ Risk & Performance":
    st.subheader("Risk & Performance")
    st.caption("Comparable historical performance across all six stocks, using bonus-adjusted prices for TCS and Infosys.")
    rows = []
    all_growth = growth_series(adjusted=True)
    for name in STOCKS:
        series = all_growth[all_growth.stock == name].sort_values("date").copy()
        values = series.growth_of_100.astype(float) / 100.0
        daily = values.pct_change().dropna()
        if len(values) < 2 or daily.empty:
            continue
        elapsed_days = (pd.to_datetime(series.date.iloc[-1]) - pd.to_datetime(series.date.iloc[0])).days
        years = max(elapsed_days / 365.25, 1/365.25)
        total_return = (values.iloc[-1] / values.iloc[0] - 1) * 100
        annual_return = ((values.iloc[-1] / values.iloc[0]) ** (1 / years) - 1) * 100 if values.iloc[-1] > 0 else -100
        annual_vol = daily.std(ddof=0) * (252 ** 0.5) * 100
        drawdown = (values / values.cummax() - 1).min() * 100
        return_risk = annual_return / annual_vol if annual_vol else float("nan")
        rows.append({"Stock": name, "Total return": total_return, "Annual return %": annual_return,
                     "Annual volatility": annual_vol, "Max drawdown": drawdown, "Return/risk": return_risk})
    score = pd.DataFrame(rows).sort_values("Annual return %", ascending=False)
    display = score.copy()
    for col in ["Total return", "Annual return %", "Annual volatility", "Max drawdown"]:
        display[col] = display[col].map(lambda x: f"{x:+.2f}%" if col in ["Total return", "Annual return %", "Max drawdown"] else f"{x:.2f}%")
    display["Return/risk"] = display["Return/risk"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
    st.dataframe(display, use_container_width=True, hide_index=True)
    left, right = st.columns(2)
    with left:
        fig = px.scatter(score, x="Annual volatility", y="Annual return %", text="Stock", size="Total return",
                         hover_data={"Max drawdown":":.2f", "Return/risk":":.2f"},
                         title="Return vs. risk", labels={"Annual volatility":"Annual volatility (%)", "Annual return %":"Annualized return (%)"})
        fig.update_traces(textposition="top center")
        fig.update_layout(height=420)
        show_chart(fig)
    with right:
        dd = score.sort_values("Max drawdown")
        fig = px.bar(dd, x="Stock", y="Max drawdown", color="Max drawdown", title="Maximum peak-to-trough drawdown",
                     labels={"Max drawdown":"Max drawdown (%)"}, color_continuous_scale="RdYlGn")
        fig.update_layout(height=420, coloraxis_showscale=False)
        show_chart(fig)
    st.caption("Annual return is CAGR. Annual volatility uses population standard deviation of daily returns × √252. Return/risk is CAGR divided by annual volatility; it is not a Sharpe ratio and does not subtract a risk-free rate.")

elif page == "📈 Strategy vs Buy & Hold":
    st.subheader("Strategy vs Buy & Hold")
    st.caption("A transparent moving-average crossover backtest compared with holding the same stock. Educational analysis only, not investment advice.")
    stock = st.selectbox("Choose stock", STOCKS, key="strategy_stock")
    table = DISPLAY_TO_TABLE[stock]
    expr = "CASE WHEN date < '2018-05-31' THEN close_price/2.0 ELSE close_price END" if stock == "TCS" else \
           "CASE WHEN date < '2015-06-15' THEN close_price/2.0 ELSE close_price END" if stock == "Infosys" else "close_price"
    data = sql_df(f"""WITH p AS (SELECT date,{expr} close_price FROM {table}),
    m AS (SELECT date,close_price,AVG(close_price) OVER(ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) ma20,
    AVG(close_price) OVER(ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) ma50,
    close_price/LAG(close_price) OVER(ORDER BY date)-1 daily_return FROM p)
    SELECT * FROM m ORDER BY date""")
    data["date"] = pd.to_datetime(data["date"])
    data["position"] = ((data.ma20 > data.ma50) & data.ma20.notna() & data.ma50.notna()).astype(int).shift(1).fillna(0)
    data["strategy_return"] = data["position"] * data["daily_return"].fillna(0)
    data["buy_hold"] = (1 + data["daily_return"].fillna(0)).cumprod() * 100
    data["strategy"] = (1 + data["strategy_return"]).cumprod() * 100
    data["buy_hold_dd"] = data["buy_hold"] / data["buy_hold"].cummax() - 1
    data["strategy_dd"] = data["strategy"] / data["strategy"].cummax() - 1
    bh_return = data.buy_hold.iloc[-1] - 100
    strat_return = data.strategy.iloc[-1] - 100
    bh_vol = data.daily_return.dropna().std(ddof=0) * (252 ** .5) * 100
    strat_vol = data.strategy_return.std(ddof=0) * (252 ** .5) * 100
    m = st.columns(4)
    m[0].metric("Buy & hold return", f"{bh_return:+.1f}%")
    m[1].metric("MA strategy return", f"{strat_return:+.1f}%", delta=f"{strat_return-bh_return:+.1f} pp vs hold")
    m[2].metric("Buy & hold annual vol.", f"{bh_vol:.1f}%")
    m[3].metric("Strategy annual vol.", f"{strat_vol:.1f}%")
    chart = data.melt(id_vars="date", value_vars=["buy_hold", "strategy"], var_name="Approach", value_name="Portfolio value (₹, start=100)")
    chart["Approach"] = chart["Approach"].map({"buy_hold":"Buy & Hold", "strategy":"MA20/MA50 Strategy"})
    fig = px.line(chart, x="date", y="Portfolio value (₹, start=100)", color="Approach", title=f"Growth of ₹100 — {stock}")
    fig.update_layout(height=450, hovermode="x unified")
    show_chart(fig)
    l, r = st.columns(2)
    with l:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data.date, y=data.buy_hold_dd*100, name="Buy & Hold drawdown", fill="tozeroy"))
        fig.add_trace(go.Scatter(x=data.date, y=data.strategy_dd*100, name="Strategy drawdown", fill="tozeroy"))
        fig.update_layout(title="Drawdown comparison", yaxis_title="Drawdown (%)", height=370, hovermode="x unified")
        show_chart(fig)
    with r:
        ret = pd.DataFrame({"Approach":["Buy & Hold","MA20/MA50 Strategy"],
                            "Total return (%)":[bh_return,strat_return],
                            "Max drawdown (%)":[data.buy_hold_dd.min()*100,data.strategy_dd.min()*100],
                            "Annual volatility (%)":[bh_vol,strat_vol]})
        fig = px.bar(ret, x="Approach", y="Total return (%)", color="Approach", title="Total return comparison", text_auto=".1f")
        fig.update_layout(height=370, showlegend=False)
        show_chart(fig)
        st.dataframe(ret.round(2), use_container_width=True, hide_index=True)
    st.info("Method: signals use 20-day and 50-day moving averages; the position is shifted by one trading day to reduce look-ahead bias. This simplified backtest excludes transaction costs, taxes, slippage, dividends and execution constraints. Historical results do not predict future performance.")

else:
    st.subheader("Live SQL Playground")
    st.caption("Edit the SQL, run it against the live in-memory SQLite database, inspect the result, and optionally chart it.")
    with st.expander("Tables and schema"):
        st.code("""bajaj_auto
eicher_motors
hero_motocorp
infosys
tcs
tvs_motors

Common columns:
date, open_price, high_price, low_price, close_price,
wap, no_of_shares, no_of_trades, total_turnover,
deliverable_qty, pct_deli_qty, spread_high_low, spread_close_open""")

    choice = st.selectbox("Query library", list(QUERIES))
    sql = st.text_area("SQL editor", QUERIES[choice], height=300)
    if st.button("▶ Run SQL", type="primary"):
        try:
            result = sql_df(sql)
            st.success(f"{len(result):,} rows returned")
            st.dataframe(result, use_container_width=True, hide_index=True)
            if not result.empty:
                numeric = [c for c in result.columns if pd.api.types.is_numeric_dtype(result[c])]
                if len(result.columns) >= 2 and numeric:
                    st.markdown("#### Optional chart")
                    x = st.selectbox("X-axis", result.columns, key="play_x")
                    y = st.selectbox("Y-axis", numeric, key="play_y")
                    chart_type = st.radio("Chart", ["Line", "Bar", "Scatter"], horizontal=True)
                    if chart_type == "Line":
                        fig = px.line(result, x=x, y=y, markers=True)
                    elif chart_type == "Bar":
                        fig = px.bar(result, x=x, y=y)
                    else:
                        fig = px.scatter(result, x=x, y=y)
                    show_chart(fig)
                st.download_button("Download result as CSV", result.to_csv(index=False),
                                   "query_result.csv", "text/csv")
        except Exception as e:
            st.error(f"SQLite error: {e}")

st.divider()
st.caption("SQL-first architecture: SQLite performs analytical calculations; Python is used for app orchestration and visualization.")