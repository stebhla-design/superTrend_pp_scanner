import os
import tempfile
import threading
import time
from datetime import datetime, timedelta
from io import StringIO

import numpy as np
import pandas as pd
import requests
import yfinance as yf

# Redirect yfinance SQLite cache to a fresh temp dir each run.
_YF_CACHE_DIR = tempfile.mkdtemp(prefix="yf_cache_")
yf.set_tz_cache_location(_YF_CACHE_DIR)

NSE_HDR = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}

FALLBACK_SYMBOLS = [
    "RELIANCE","HDFCBANK","BHARTIARTL","SBIN","ICICIBANK","TCS","BAJFINANCE",
    "HINDUNILVR","INFY","LT","ITC","SUNPHARMA","AXISBANK","KOTAKBANK","TITAN",
    "HCLTECH","MARUTI","NTPC","ULTRACEMCO","WIPRO","ASIANPAINT","M&M","POWERGRID",
    "TECHM","NESTLEIND","BAJAJFINSV","TATAMOTORS","TATASTEEL","JSWSTEEL","HINDALCO",
    "ADANIENT","ADANIPORTS","COALINDIA","ONGC","GRASIM","BPCL","HEROMOTOCO",
    "DIVISLAB","DRREDDY","CIPLA","APOLLOHOSP","EICHERMOT","BRITANNIA","DABUR",
    "PIDILITIND","SIEMENS","ABB","HAVELLS","POLYCAB","MOTHERSON","DMART",
    "NAUKRI","IRFC","IRCTC","RVNL","NHPC","SJVN","RECLTD","PFC",
    "BANKBARODA","CANBK","PNB","UNIONBANK","IDFCFIRSTB","FEDERALBNK","BANDHANBNK",
    "PERSISTENT","MPHASIS","COFORGE","LTIM","OFSS","CHOLAFIN","BAJAJ-AUTO",
    "TVSMOTORS","EXIDEIND","AMBUJACEM","ACC","VOLTAS","TRENT","MUTHOOTFIN",
    "GODREJCP","MARICO","COLPAL","INDIGO","ZYDUSLIFE","LUPIN","TORNTPHARM",
    "AUROPHARMA","BIOCON","GLENMARK","IPCALAB","SAIL","NMDC","VEDL","HINDCOPPER",
    "TATAPOWER","ADANIGREEN","CESC","TORNTPOWER","JSWENERGY","DLF","GODREJPROP",
    "OBEROIRLTY","PRESTIGE","MFSL","ICICIGI","HDFCLIFE","SBILIFE","LICI",
    "DIXON","KAYNES","LTTS","KPITTECH","TATAELXSI","CONCOR","PHOENIXLTD",
    "HUDCO","NATIONALUM","PIIND","ASTRAL","GRINDWELL","CUMMINSIND","THERMAX",
    "SUNDARMFIN","DEEPAKNTR","ATUL","BLUESTARCO","CROMPTON","ORIENTELEC",
    "JSWINFRA","ADANIPOWER","TATACOMM","HFCL","RAILTEL","LALPATHLAB",
]

PERIOD = 10
MULTIPLIER = 3.0
FETCH_DAYS = 250


def load_symbols(csv_path: str = "ind_nifty500list.csv") -> list[str]:
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path, usecols=["Symbol"], dtype=str)
        symbols = df["Symbol"].dropna().str.strip().unique().tolist()
        return [s for s in symbols if s]

    try:
        url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
        r = requests.get(url, headers=NSE_HDR, timeout=15)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text), usecols=["Symbol"], dtype=str)
        return df["Symbol"].dropna().str.strip().unique().tolist()
    except Exception:
        return FALLBACK_SYMBOLS


def fetch_ohlc(symbol: str) -> pd.DataFrame | None:
    ticker = f"{symbol}.NS"
    end = datetime.today() + timedelta(days=1)
    start = end - timedelta(days=FETCH_DAYS + 60)

    try:
        raw = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
            actions=False,
        )

        if raw is None or raw.empty:
            return None

        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0] for c in raw.columns]

        needed = ["Open", "High", "Low", "Close"]
        if not all(c in raw.columns for c in needed):
            return None

        df = raw[needed].dropna().copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df
    except Exception:
        return None


def calc_supertrend(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int, multiplier: float):
    n = len(close)
    hl2 = (high + low) / 2.0

    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )

    atr = np.empty(n)
    atr[0] = tr[0]
    for i in range(1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    upper = np.empty(n)
    lower = np.empty(n)
    upper[0] = basic_upper[0]
    lower[0] = basic_lower[0]

    for i in range(1, n):
        upper[i] = basic_upper[i] if basic_upper[i] < upper[i - 1] or close[i - 1] > upper[i - 1] else upper[i - 1]
        lower[i] = basic_lower[i] if basic_lower[i] > lower[i - 1] or close[i - 1] < lower[i - 1] else lower[i - 1]

    st = np.empty(n)
    direction = np.empty(n, dtype=bool)
    st[0] = upper[0]
    direction[0] = False

    for i in range(1, n):
        prev_st_was_upper = st[i - 1] == upper[i - 1]
        if prev_st_was_upper:
            if close[i] > upper[i]:
                direction[i] = True
                st[i] = lower[i]
            else:
                direction[i] = False
                st[i] = upper[i]
        else:
            if close[i] < lower[i]:
                direction[i] = False
                st[i] = upper[i]
            else:
                direction[i] = True
                st[i] = lower[i]

    return direction, st, upper, lower


def calc_pivots(ph: float, pl: float, pc: float) -> dict[str, float]:
    pp = (ph + pl + pc) / 3.0
    return {
        "PP": pp,
        "R1": 2 * pp - pl,
        "R2": pp + (ph - pl),
        "R3": ph + 2 * (pp - pl),
        "S1": 2 * pp - ph,
        "S2": pp - (ph - pl),
        "S3": pl - 2 * (ph - pp),
    }


def get_prev_month_ohlc(df: pd.DataFrame) -> tuple[float, float, float, float] | tuple[None, None, None, None]:
    monthly = df.resample("ME").agg(
        Open=("Open", "first"),
        High=("High", "max"),
        Low=("Low", "min"),
        Close=("Close", "last"),
    ).dropna()

    if monthly.empty or len(monthly) < 1:
        return None, None, None, None

    today = df.index[-1]
    last_month_end = monthly.index[-1]

    if last_month_end.month == today.month and last_month_end.year == today.year:
        if len(monthly) < 2:
            return None, None, None, None
        prev = monthly.iloc[-2]
    else:
        prev = monthly.iloc[-1]

    return float(prev["High"]), float(prev["Low"]), float(prev["Close"]), float(prev["Open"])


def analyse(symbol: str) -> dict | None:
    df = fetch_ohlc(symbol)
    if df is None or len(df) < PERIOD + 5:
        return None

    hi = df["High"].to_numpy(dtype=float)
    lo = df["Low"].to_numpy(dtype=float)
    cl = df["Close"].to_numpy(dtype=float)

    direction, st, upper, lower = calc_supertrend(hi, lo, cl, PERIOD, MULTIPLIER)
    today_close = float(cl[-1])
    prev_close = float(cl[-2])

    ph, pl, pc, _ = get_prev_month_ohlc(df)
    if ph is None:
        return None

    pivots = calc_pivots(ph, pl, pc)
    pp, r1, r2, s1 = pivots["PP"], pivots["R1"], pivots["R2"], pivots["S1"]
    r1_first_cross = today_close > r1 and prev_close <= r1
    is_bullish = bool(direction[-1])

    signal = None
    if is_bullish:
        if r1_first_cross:
            signal = "PRIMARY ✅"
        elif today_close > r1:
            signal = "ABOVE R1 ⏳"
        elif today_close > pp:
            signal = "SECONDARY 🟡"

    if signal is None:
        return None

    return {
        "Symbol": symbol,
        "Date": df.index[-1].strftime("%Y-%m-%d"),
        "Close": round(today_close, 2),
        "Prev_Close": round(prev_close, 2),
        "ST_Line": round(float(st[-1]), 2),
        "Signal": signal,
        "Pivot(PP)": round(pp, 2),
        "R1": round(r1, 2),
        "R2": round(r2, 2),
        "S1": round(s1, 2),
        "%_vs_PP": round((today_close - pp) / pp * 100, 2),
        "%_vs_R1": round((today_close - r1) / r1 * 100, 2),
        "Target(+10%)": round(today_close * 1.10, 2),
        "SL(-5%)": round(today_close * 0.95, 2),
    }


def run_scan(symbols: list[str], state: dict, delay: float = 2.0) -> None:
    while state["index"] < len(symbols) and not state["stop_event"].is_set():
        symbol = symbols[state["index"]]
        state["current_symbol"] = symbol
        state["status"] = "Scanning"
        result = analyse(symbol)

        if result is not None:
            state["results"].append(result)

        state["processed"] += 1
        state["index"] += 1
        state["last_update"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state["status"] = "Paused" if state["stop_event"].is_set() else "Running"

        for _ in range(int(delay * 10)):
            if state["stop_event"].is_set():
                break
            time.sleep(0.1)

    if state["stop_event"].is_set():
        state["status"] = "Stopped"
    else:
        state["status"] = "Complete"


def build_state() -> dict:
    return {
        "results": [],
        "status": "Stopped",
        "current_symbol": "",
        "processed": 0,
        "index": 0,
        "started_at": None,
        "last_update": None,
        "stop_event": threading.Event(),
        "thread": None,
    }
