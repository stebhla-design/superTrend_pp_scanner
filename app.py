import threading
from datetime import datetime

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from scanner import build_state, load_symbols, run_scan

st.set_page_config(
    page_title="Nifty 500 Scanner Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="📈",
)

DASHBOARD_CSS = """
<style>
body, .main, .block-container {
    background: #020617;
    color: #e2e8f0;
}
[data-testid="stSidebar"] {
    background: #0f1720;
    color: #cbd5e1;
}
[data-testid="stSidebar"] .css-1d391kg {
    padding-top: 0.5rem;
}
.stButton>button {
    background-color: #0ea5e9 !important;
    color: #ffffff !important;
    border-radius: 10px !important;
    padding: 0.7rem 1rem !important;
    border: none !important;
    box-shadow: 0 14px 30px rgba(14, 165, 233, 0.15) !important;
    margin: 0.18rem 0 !important;
}
.stButton>button:hover {
    background-color: #22d3ee !important;
}
.tight-divider {
    margin: 0.35rem 0;
    border-top: 1px solid rgba(148, 163, 184, 0.18);
}
.sidebar-section-title {
    margin: 0.25rem 0 0.35rem 0;
    font-size: 1rem;
    font-weight: 700;
    color: #f8fafc;
}
.metric-card, .panel-card {
    background: #111827;
    border: 1px solid rgba(148, 163, 184, 0.16);
    border-radius: 18px;
    padding: 1rem;
    box-shadow: 0 18px 45px rgba(15, 23, 42, 0.16);
}
.metric-card .metric-label {
    color: #94a3b8;
    font-size: 0.9rem;
    margin-bottom: 0.2rem;
}
.metric-card .metric-value {
    color: #f8fafc;
    font-size: 2rem;
    font-weight: 700;
}
.metric-card .metric-note {
    color: #94a3b8;
    margin-top: 0.25rem;
    font-size: 0.85rem;
}
.dashboard-title {
    font-size: 2.25rem;
    font-weight: 800;
    color: #f8fafc;
    margin-bottom: 0.1rem;
}
.dashboard-subtitle {
    color: #cbd5e1;
    margin-top: 0;
    margin-bottom: 0.5rem;
    font-size: 1rem;
    line-height: 1.6;
}
.status-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.35rem;
    padding: 0.55rem 0.85rem;
    border-radius: 999px;
    font-size: 0.9rem;
    font-weight: 700;
    color: #f8fafc;
}
.badge {
    display: inline-flex;
    align-items: center;
    padding: 0.35rem 0.65rem;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 700;
    color: #f8fafc;
}
.badge-primary { background: #0f766e; }
.badge-warning { background: #c2410c; }
.badge-neutral { background: #713f12; }
.badge-info { background: #0284c7; }
.table-title {
    color: #cbd5e1;
    font-size: 1rem;
    margin-bottom: 0.25rem;
}
[data-testid="stDataFrame"] {
    border-radius: 18px;
    overflow: hidden;
}
[data-testid="stDataFrame"] table {
    background: #020617;
}
[data-testid="stDataFrame"] th {
    color: #cbd5e1;
    background: #111827;
}
[data-testid="stDataFrame"] td {
    color: #e2e8f0;
}
hr {
    margin: 0.5rem 0;
}
</style>
"""

st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)

if "scan_state" not in st.session_state:
    st.session_state.scan_state = build_state()

if "symbols" not in st.session_state:
    st.session_state.symbols = load_symbols("ind_nifty500list.csv")

if "scanner_type" not in st.session_state:
    st.session_state.scanner_type = "Select One"

if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = True

if "refresh_interval" not in st.session_state:
    st.session_state.refresh_interval = 10

state = st.session_state.scan_state
symbols = st.session_state.symbols


def get_market_status() -> tuple[str, str]:
    now = datetime.now()
    if 9 <= now.hour < 15:
        return "LIVE", "#10b981"
    return "CLOSED", "#f59e0b"


def format_kpi(label: str, value: str, note: str) -> str:
    return f"""
<div class='metric-card'>
  <div class='metric-label'>{label}</div>
  <div class='metric-value'>{value}</div>
  <div class='metric-note'>{note}</div>
</div>
"""


def render_header() -> None:
    market_status, status_color = get_market_status()
    last_update = state["last_update"] or "Pending"
    header_left, header_right = st.columns([3, 1], gap="small")

    with header_left:
        st.markdown("<div class='dashboard-title'>Nifty 500 SuperTrend Scanner</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='dashboard-subtitle'>Live Nifty 500 scanning with SuperTrend(10,3) and Monthly Pivot R1 focus. Designed for fast signal review and actionable setups.</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<div class='status-pill' style='background:{status_color};'>Market {market_status}</div>"
            f" <span style='color:#94a3b8; margin-left:0.5rem;'>Last updated: {last_update}</span>",
            unsafe_allow_html=True,
        )

    with header_right:
        if st.button("Refresh dashboard", key="header_refresh"):
            if hasattr(st, "experimental_rerun"):
                st.experimental_rerun()
        st.markdown(
            "<div style='margin-top:0.35rem; color:#94a3b8;'>Use the sidebar to control scan settings, refresh cadence, and scan actions.</div>",
            unsafe_allow_html=True,
        )


def apply_scan() -> None:
    if st.session_state.scanner_type == "Select One":
        st.warning("Select a scanner strategy before starting the scan.")
        return

    if state["thread"] is None or not state["thread"].is_alive():
        if state["index"] >= len(symbols):
            state.update(build_state())
        state["stop_event"].clear()
        state["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state["status"] = "Starting"
        thread = threading.Thread(target=run_scan, args=(symbols, state, 2.0))
        thread.daemon = True
        state["thread"] = thread
        thread.start()
    else:
        st.info("Scan is already running.")


def reset_filters() -> None:
    st.session_state.scanner_type = "Select One"
    st.session_state.auto_refresh = True
    st.session_state.refresh_interval = 10


def render_sidebar() -> None:
    st.sidebar.title("Scan Controls")
    st.sidebar.markdown("<hr class='tight-divider'/>", unsafe_allow_html=True)
    st.sidebar.markdown("<div class='sidebar-section-title'>Market / Universe</div>", unsafe_allow_html=True)
    st.sidebar.selectbox(
        "Scanner strategy",
        ["Select One", "Daily Super Trend + Pivot Strategy"],
        key="scanner_type",
    )
    st.sidebar.markdown(f"**Symbols loaded:** {len(symbols)}")

    st.sidebar.markdown("<hr class='tight-divider'/>", unsafe_allow_html=True)
    st.sidebar.markdown("<div class='sidebar-section-title'>Actions</div>", unsafe_allow_html=True)
    if st.sidebar.button("Apply scan", key="apply_scan"):
        apply_scan()
    if st.sidebar.button("Start scan", key="start_scan"):
        apply_scan()
    if st.sidebar.button("Stop scan", key="stop_scan"):
        if state["thread"] is not None and state["thread"].is_alive():
            state["stop_event"].set()
            state["status"] = "Stopping"
        else:
            st.sidebar.warning("Scanner is not running.")
    if st.sidebar.button("Resume scan", key="resume_scan"):
        if state["status"] in ["Stopped", "Paused"] and state["index"] < len(symbols):
            if state["thread"] is None or not state["thread"].is_alive():
                state["stop_event"].clear()
                if state["started_at"] is None:
                    state["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                state["status"] = "Resuming"
                thread = threading.Thread(target=run_scan, args=(symbols, state, 2.0))
                thread.daemon = True
                state["thread"] = thread
                thread.start()
        else:
            st.sidebar.warning("No paused scan to resume.")

    st.sidebar.markdown("<hr class='tight-divider'/>", unsafe_allow_html=True)
    st.sidebar.markdown("<div class='sidebar-section-title'>Refresh & Scan Timing</div>", unsafe_allow_html=True)
    st.sidebar.checkbox("Auto-refresh dashboard", key="auto_refresh")
    st.sidebar.number_input(
        "Refresh interval (sec)",
        min_value=2,
        max_value=60,
        value=st.session_state.refresh_interval,
        step=1,
        key="refresh_interval",
    )
    st.sidebar.markdown("<small>Auto-refresh updates the scan table without navigating away.</small>", unsafe_allow_html=True)

    st.sidebar.markdown("<hr class='tight-divider'/>", unsafe_allow_html=True)
    if st.sidebar.button("Reset filters", key="reset_filters"):
        reset_filters()
    st.sidebar.markdown("<small>Reset sidebar selections to defaults.</small>", unsafe_allow_html=True)


def style_signal(value: str) -> str:
    if isinstance(value, str):
        if "PRIMARY" in value:
            return "color: #4ade80; font-weight: 700;"
        if "ABOVE R1" in value:
            return "color: #38bdf8; font-weight: 600;"
        if "SECONDARY" in value:
            return "color: #facc15; font-weight: 600;"
    return ""


def style_signal_column(series: pd.Series) -> pd.Series:
    return series.apply(style_signal)


def get_tradingview_link(symbol: str) -> str:
    if symbol.endswith(".NS"):
        ticker = symbol[:-3]
        return f"https://www.tradingview.com/symbols/NSE-{ticker}/"
    if symbol.endswith(".BO"):
        ticker = symbol[:-3]
        return f"https://www.tradingview.com/symbols/BOM-{ticker}/"
    safe_symbol = symbol.replace(".", "-")
    return f"https://www.tradingview.com/symbols/{safe_symbol}/"


def render_tradingview_widget(symbol: str) -> None:
    if not symbol:
        return

    if symbol.endswith(".NS"):
        market = "NSE"
        code = symbol[:-3]
    elif symbol.endswith(".BO"):
        market = "BOM"
        code = symbol[:-3]
    else:
        market = ""
        code = symbol

    tv_symbol = f"{market}:{code}" if market else code
    safe_id = symbol.replace(".", "-").replace(":", "-")
    chart_html = f"""
    <div class='tradingview-widget-container' style='height: 520px;'>
      <div id='tradingview_{safe_id}'></div>
      <script type='text/javascript' src='https://s3.tradingview.com/tv.js'></script>
      <script type='text/javascript'>
      new TradingView.widget({{
        "autosize": true,
        "symbol": "{tv_symbol}",
        "interval": "D",
        "timezone": "Etc/UTC",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "toolbar_bg": "#0f1720",
        "enable_publishing": false,
        "allow_symbol_change": true,
        "container_id": "tradingview_{safe_id}"
      }});
      </script>
    </div>
    """
    st.components.v1.html(chart_html, height=540, scrolling=False)


def style_results_table(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    return (
        df.style
        .format({"Close": "{:.2f}", "Prev_Close": "{:.2f}", "%_vs_PP": "{:+.2f}%", "%_vs_R1": "{:+.2f}%", "Target(+10%)": "{:.2f}", "SL(-5%)": "{:.2f}"})
        .apply(style_signal_column, subset=["Signal"])
        .set_properties(**{"font-size": "0.92rem", "padding": "0.4rem 0.5rem"})
    )


def render_results_tab() -> None:
    df_results = pd.DataFrame(state["results"])
    df_primary = df_results[df_results["Signal"].str.contains("PRIMARY", na=False)].copy() if not df_results.empty else pd.DataFrame()
    filtered = df_primary

    search_value = st.text_input("Search symbols or signal", value="", placeholder="Search symbol, signal, or target")
    if search_value and not filtered.empty:
        query = search_value.strip().upper()
        filtered = filtered[filtered["Symbol"].str.contains(query) | filtered["Signal"].str.contains(query)]

    summary_text = f"{len(filtered)} PRIMARY matches out of {len(symbols)} symbols scanned."
    st.markdown(f"<div class='table-title'>{summary_text}</div>", unsafe_allow_html=True)

    if filtered.empty:
        st.markdown(
            "<div class='panel-card'><strong>No PRIMARY signals found yet.</strong> Start the scan or wait for a fresh cycle.</div>",
            unsafe_allow_html=True,
        )
        return

    filtered = filtered.sort_values(by=["%_vs_R1", "%_vs_PP"], ascending=[False, False])
    display_df = filtered.copy()
    display_df["Symbol"] = display_df["Symbol"].apply(
        lambda s: f"<a href='{get_tradingview_link(s)}' target='_blank'>{s}</a>"
    )

    styled = style_results_table(display_df)
    st.markdown(styled.to_html(escape=False), unsafe_allow_html=True)

    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download PRIMARY results CSV",
        data=csv,
        file_name="nifty500_primary_scan_results.csv",
        mime="text/csv",
    )

    chart_symbol = st.selectbox(
        "Embedded TradingView chart for",
        filtered["Symbol"].tolist(),
        index=0,
        key="tv_chart_symbol",
    )
    render_tradingview_widget(chart_symbol)


def render_signal_summary_tab() -> None:
    df_results = pd.DataFrame(state["results"])
    if df_results.empty:
        st.info("No scan data available yet. Run the scan to populate the summary.")
        return

    primary_count = len(df_results[df_results["Signal"].str.contains("PRIMARY", na=False)])
    total_processed = state["processed"]
    summary_columns = st.columns(3, gap="small")
    summary_columns[0].metric("Signals found", primary_count)
    summary_columns[1].metric("Total scanned", total_processed)
    summary_columns[2].metric("Remaining", max(0, len(symbols) - total_processed))

    st.markdown("<div class='panel-card'><strong>Primary R1 breakout review</strong><br />The summary table below lists signal counts and status for the current scan run.</div>", unsafe_allow_html=True)
    top_signals = df_results["Signal"].value_counts().rename_axis("Signal").reset_index(name="Count")
    st.dataframe(top_signals, use_container_width=True)


def render_help_tab() -> None:
    st.subheader("Methodology & usage")
    st.markdown(
        """
- Strategy: SuperTrend(10,3) plus Monthly Pivot R1 breakout.
- Only PRIMARY signals are surfaced when the latest close crosses above R1.
- The app fetches Yahoo Finance OHLC for Nifty 500 symbols and scans in the background thread.
- Use the sidebar to control scan type, refresh cadence, and run / pause behavior.
- Keep scan cadence around 2 seconds per symbol to reduce API throttling.
""",
    )
    st.markdown(
        "<div class='panel-card'><strong>Tip:</strong> If the dashboard is idle, refresh manually or enable auto-refresh to keep the table current.</div>",
        unsafe_allow_html=True,
    )


render_sidebar()
render_header()

if st.session_state.auto_refresh:
    st_autorefresh(interval=st.session_state.refresh_interval * 1000, key="live_refresh")

kpi1 = format_kpi("Universe", f"{len(symbols)}", "Total Nifty 500 symbols")
kpi2 = format_kpi("Processed", f"{state['processed']} / {len(symbols)}", "Symbols scanned so far")
kpi3 = format_kpi("Matches", f"{len(state['results'])}", "Primary signals captured")
kpi4 = format_kpi("Strong setups", f"{len(state['results'])}", "Fresh bullish breakouts")

cols = st.columns(4, gap="large")
for index, markup in enumerate([kpi1, kpi2, kpi3, kpi4]):
    cols[index].markdown(markup, unsafe_allow_html=True)

st.markdown("---")

scan_tab, summary_tab, help_tab = st.tabs(["Scan Results", "Signal Summary", "Help / Methodology"])

with scan_tab:
    render_results_tab()

with summary_tab:
    render_signal_summary_tab()

with help_tab:
    render_help_tab()
