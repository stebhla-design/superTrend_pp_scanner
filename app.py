import threading
import time
from datetime import datetime

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from scanner import build_state, load_symbols, run_scan

st.set_page_config(
    page_title="Nifty 500 Scanner Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    "<h1 style='color: #FF8C00; margin-bottom: 0;'>📊 Nifty Scanner</h1>",
    unsafe_allow_html=True
)

if "scan_state" not in st.session_state:
    st.session_state.scan_state = build_state()

if "symbols" not in st.session_state:
    st.session_state.symbols = load_symbols("ind_nifty500list.csv")

state = st.session_state.scan_state
symbols = st.session_state.symbols

refresh_col1, refresh_col2 = st.columns([3, 1])
with refresh_col1:
    st.write("")
with refresh_col2:
    st.write("**Settings**")
    auto_refresh = st.checkbox("Enable auto-refresh", value=True)
    refresh_interval = st.number_input("Refresh every (seconds)", min_value=2, max_value=60, value=10, step=1)
    if st.button("Refresh dashboard"):
        pass

st.markdown("---")

col1, col2 = st.columns([1, 2])
with col1:
    st.header("Scanner Controls")
    st.write("Use the buttons below to start, stop, or resume the live scan.")
    
    scanner_type = st.selectbox(
        "Scanner Type",
        ["Select One", "Daily Super Trend + Pivot Strategy"]
    )
    st.write(f"Selected: **{scanner_type}**")

    is_disabled = scanner_type == "Select One"

    if st.button("Start scanner", disabled=is_disabled):
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
            st.warning("Scanner is already running.")

    if st.button("Stop scanner", disabled=is_disabled):
        if state["thread"] is not None and state["thread"].is_alive():
            state["stop_event"].set()
            state["status"] = "Stopping"
        else:
            st.warning("Scanner is not currently running.")

    if st.button("Resume scanner", disabled=is_disabled):
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
            st.warning("No paused scan to resume.")

    st.markdown("---")
    st.subheader("Scanner status")
    st.metric("Status", state["status"])
    st.metric("Processed", f"{state['processed']} / {len(symbols)}")
    st.metric("Hits found", len(state["results"]))
    st.write(f"Current symbol: {state['current_symbol'] or 'N/A'}")
    st.write(f"Last update: {state['last_update'] or 'N/A'}")
    st.write(f"Started at: {state['started_at'] or 'N/A'}")

with col2:
    st.subheader("Live scan results — PRIMARY signals only")
    if state["results"]:
        df_results = pd.DataFrame(state["results"])
        df_primary = df_results[df_results["Signal"].str.contains("PRIMARY")].copy()
        if not df_primary.empty:
            df_primary = df_primary.sort_values(by=["%_vs_R1", "%_vs_PP"], ascending=[False, False])
            st.dataframe(df_primary, use_container_width=True)
            csv = df_primary.to_csv(index=False).encode("utf-8")
            st.download_button("Download PRIMARY results CSV", data=csv, file_name="nifty500_primary_scan_results.csv", mime="text/csv")
        else:
            st.markdown("<p style='color: #FF8C00;'><b>No PRIMARY signals found yet. Start the scanner or wait for new data.</b></p>", unsafe_allow_html=True)
    else:
        st.markdown("<p style='color: #FF8C00;'><b>No live matches found yet. Start the scanner to begin fetching results.</b></p>", unsafe_allow_html=True)

if auto_refresh:
    refresh_counter = st_autorefresh(interval=refresh_interval * 1000, key="live_refresh")

st.markdown("---")

st.subheader("Scanner tips")
st.write(
    "- Ensure you are connected to the internet.\n"
    "- The app fetches live OHLC from Yahoo Finance for each symbol.\n"
    "- Use Stop to pause the scan and Resume to continue from the last symbol.\n"
    "- Reload symbols after updating `ind_nifty500list.csv` if needed."
)
