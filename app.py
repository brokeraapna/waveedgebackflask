"""
WaveEdge Backend - Fresh Start
Pure Upstox API - No Yahoo Finance
"""
from flask import Flask, jsonify, request, redirect
from flask_cors import CORS
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import threading, time, logging, json, os, re
import requests

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("waveedge")

app = Flask(__name__)
CORS(app)

# ── CONFIG ────────────────────────────────────────────────
CLIENT_ID     = os.environ.get("UPSTOX_API_KEY",       "952b375b-2750-4bd0-827d-ffe1cd44a8b8")
CLIENT_SECRET = os.environ.get("UPSTOX_API_SECRET",    "")
REDIRECT_URI  = os.environ.get("REDIRECT_URL",         "https://waveedgebackflask-2.onrender.com/upstox/callback")
ADMIN_KEY     = os.environ.get("ADMIN_KEY",             "waveedge2024")
SELF_URL      = os.environ.get("FRONTEND_URL",          "https://waveedgebackflask-2.onrender.com")
TOKEN_FILE    = "upstox_token.json"
POSTS_FILE    = "blog_posts.json"

# ── TOKEN ─────────────────────────────────────────────────
_tok = {}

def load_token():
    global _tok
    # First try environment variable (survives Render restarts)
    env_token = os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip()
    if env_token:
        _tok = {"access_token": env_token, "expires_at": date.today().isoformat()}
        log.info("Token loaded from environment variable")
        return
    # Fall back to file
    try:
        with open(TOKEN_FILE) as f:
            _tok = json.load(f)
        log.info(f"Token loaded from file, expires: {_tok.get('expires_at','?')}")
    except:
        _tok = {}
        log.warning("No token found - please reconnect Upstox")

def save_token(data):
    global _tok
    _tok = data
    # Save to file
    try:
        with open(TOKEN_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        log.error(f"Token save error: {e}")
    # Also update environment variable in memory
    if data.get('access_token'):
        os.environ["UPSTOX_ACCESS_TOKEN"] = data['access_token']
        log.info("Token saved to file and environment")

def get_token():
    if not _tok.get('access_token'):
        return None
    exp = _tok.get('expires_at', '')
    if exp and exp < date.today().isoformat():
        log.warning("Token expired - please reconnect Upstox")
        return None
    return _tok['access_token']

def exchange_code(code):
    try:
        log.info(f"Exchanging code: {code[:8]}...")
        log.info(f"Client ID: {CLIENT_ID}")
        log.info(f"Secret set: {bool(CLIENT_SECRET)} len={len(CLIENT_SECRET)}")
        log.info(f"Redirect URI: {REDIRECT_URI}")
        r = requests.post(
            "https://api.upstox.com/v2/login/authorization/token",
            data={
                "code":          code,
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uri":  REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15
        )
        log.info(f"Upstox response: {r.status_code} — {r.text[:300]}")
        if r.status_code == 200:
            data = r.json()
            data['expires_at'] = date.today().isoformat()
            save_token(data)
            log.info("✅ Upstox token saved!")
            return True, None
        return False, f"HTTP {r.status_code}: {r.text}"
    except Exception as e:
        log.error(f"Exchange error: {e}")
        return False, str(e)

# ── INSTRUMENT MAP (Upstox keys) ──────────────────────────
INSTRUMENTS = {
    # Indices
    "NIFTY":      "NSE_INDEX|Nifty 50",
    "NIFTY50":    "NSE_INDEX|Nifty 50",
    "BANKNIFTY":  "NSE_INDEX|Nifty Bank",
    "FINNIFTY":   "NSE_INDEX|Nifty Fin Service",
    "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
    "SENSEX":     "BSE_INDEX|SENSEX",
    # Large Cap NSE
    "RELIANCE":   "NSE_EQ|INE002A01018",
    "TCS":        "NSE_EQ|INE467B01029",
    "HDFCBANK":   "NSE_EQ|INE040A01034",
    "INFY":       "NSE_EQ|INE009A01021",
    "SBIN":       "NSE_EQ|INE062A01020",
    "ICICIBANK":  "NSE_EQ|INE090A01021",
    "HINDUNILVR": "NSE_EQ|INE030A01027",
    "AXISBANK":   "NSE_EQ|INE238A01034",
    "BAJFINANCE": "NSE_EQ|INE296A01024",
    "KOTAKBANK":  "NSE_EQ|INE237A01028",
    "LT":         "NSE_EQ|INE018A01030",
    "TATAMOTORS": "NSE_EQ|INE155A01022",
    "WIPRO":      "NSE_EQ|INE075A01022",
    "ADANIENT":   "NSE_EQ|INE423A01024",
    "MARUTI":     "NSE_EQ|INE585B01010",
    "SUNPHARMA":  "NSE_EQ|INE044A01036",
    "TITAN":      "NSE_EQ|INE280A01028",
    "ULTRACEMCO": "NSE_EQ|INE481G01011",
    "ASIANPAINT": "NSE_EQ|INE021A01026",
    "ITC":        "NSE_EQ|INE154A01025",
    "ONGC":       "NSE_EQ|INE213A01029",
    "NTPC":       "NSE_EQ|INE733E01010",
    "POWERGRID":  "NSE_EQ|INE752E01010",
    "NESTLEIND":  "NSE_EQ|INE239A01016",
    "TECHM":      "NSE_EQ|INE669C01036",
    "HCLTECH":    "NSE_EQ|INE860A01027",
    "BPCL":       "NSE_EQ|INE029A01011",
    "COALINDIA":  "NSE_EQ|INE522F01014",
    "BAJAJFINSV": "NSE_EQ|INE918I01026",
    "DIVISLAB":   "NSE_EQ|INE361B01024",
    "DRREDDY":    "NSE_EQ|INE089A01023",
    "EICHERMOT":  "NSE_EQ|INE066A01021",
    "GRASIM":     "NSE_EQ|INE047A01021",
    "HEROMOTOCO": "NSE_EQ|INE158A01026",
    "INDUSINDBK": "NSE_EQ|INE095A01012",
    "JSWSTEEL":   "NSE_EQ|INE019A01038",
    "M&M":        "NSE_EQ|INE101A01026",
    "SBILIFE":    "NSE_EQ|INE123W01016",
    "TATACONSUM": "NSE_EQ|INE192A01025",
    "TATASTEEL":  "NSE_EQ|INE081A01020",
    "HDFCLIFE":   "NSE_EQ|INE795G01014",
    "APOLLOHOSP": "NSE_EQ|INE437A01024",
    "BRITANNIA":  "NSE_EQ|INE216A01030",
    "CIPLA":      "NSE_EQ|INE059A01026",
    "PIDILITIND": "NSE_EQ|INE318A01026",
    "SIEMENS":    "NSE_EQ|INE003A01024",
    "VEDL":       "NSE_EQ|INE205A01025",
    "BANKBARODA": "NSE_EQ|INE028A01039",
    "PNB":        "NSE_EQ|INE160A01022",
    "SAIL":       "NSE_EQ|INE114A01011",
    "TATAPOWER":  "NSE_EQ|INE245A01021",
    "ADANIPORTS": "NSE_EQ|INE742F01042",

    # ── NSE F&O STOCKS (200+) ─────────────────────────────────
    "AARTIIND":   "NSE_EQ|INE769A01020",
    "ABB":        "NSE_EQ|INE117A01022",
    "ABBOTINDIA": "NSE_EQ|INE358A01014",
    "ABCAPITAL":  "NSE_EQ|INE674K01013",
    "ABFRL":      "NSE_EQ|INE647O01011",
    "ACC":        "NSE_EQ|INE012A01025",
    "ADANIGREEN": "NSE_EQ|INE364U01010",
    "ADANIPORTS": "NSE_EQ|INE742F01042",
    "ADANIPOWER": "NSE_EQ|INE814H01011",
    "ATGL":       "NSE_EQ|INE399L01023",
    "ALKEM":      "NSE_EQ|INE540L01014",
    "AMBUJACEM":  "NSE_EQ|INE079A01024",
    "APOLLOHOSP": "NSE_EQ|INE437A01024",
    "APOLLOTYRE": "NSE_EQ|INE438A01022",
    "AUROPHARMA": "NSE_EQ|INE406A01037",
    "AUBANK":     "NSE_EQ|INE949L01017",
    "BAJAJ-AUTO": "NSE_EQ|INE917I01010",
    "BAJAJFINSV": "NSE_EQ|INE918I01026",
    "BAJFINANCE": "NSE_EQ|INE296A01024",
    "BALKRISIND": "NSE_EQ|INE787D01026",
    "BANDHANBNK": "NSE_EQ|INE545U01014",
    "BANKBARODA": "NSE_EQ|INE028A01039",
    "BATAINDIA":  "NSE_EQ|INE176A01028",
    "BEL":        "NSE_EQ|INE263A01024",
    "BERGEPAINT": "NSE_EQ|INE463A01038",
    "BHARATFORG": "NSE_EQ|INE465A01025",
    "BHARTIARTL": "NSE_EQ|INE397D01024",
    "BHEL":       "NSE_EQ|INE257A01026",
    "BIOCON":     "NSE_EQ|INE376G01013",
    "BOSCHLTD":   "NSE_EQ|INE323A01026",
    "BPCL":       "NSE_EQ|INE029A01011",
    "BRITANNIA":  "NSE_EQ|INE216A01030",
    "BSOFT":      "NSE_EQ|INE386C01029",
    "CANBK":      "NSE_EQ|INE476A01014",
    "CANFINHOME": "NSE_EQ|INE477A01020",
    "CHAMBLFERT": "NSE_EQ|INE085A01013",
    "CHOLAFIN":   "NSE_EQ|INE121A01024",
    "CIPLA":      "NSE_EQ|INE059A01026",
    "COALINDIA":  "NSE_EQ|INE522F01014",
    "COFORGE":    "NSE_EQ|INE591G01017",
    "COLPAL":     "NSE_EQ|INE259A01022",
    "CONCOR":     "NSE_EQ|INE111A01025",
    "COROMANDEL": "NSE_EQ|INE169A01031",
    "CROMPTON":   "NSE_EQ|INE kronos0A01027",
    "CUMMINSIND": "NSE_EQ|INE298A01020",
    "DABUR":      "NSE_EQ|INE016A01026",
    "DALBHARAT":  "NSE_EQ|INE495G01014",
    "DEEPAKNTR":  "NSE_EQ|INE288B01029",
    "DELTACORP":  "NSE_EQ|INE482A01020",
    "DIVISLAB":   "NSE_EQ|INE361B01024",
    "DIXON":      "NSE_EQ|INE935N01020",
    "DLF":        "NSE_EQ|INE271C01023",
    "DRREDDY":    "NSE_EQ|INE089A01023",
    "EICHERMOT":  "NSE_EQ|INE066A01021",
    "ESCORTS":    "NSE_EQ|INE042A01014",
    "EXIDEIND":   "NSE_EQ|INE302A01020",
    "FEDERALBNK": "NSE_EQ|INE171A01029",
    "FINNIFTY":   "NSE_INDEX|Nifty Fin Service",
    "FORTIS":     "NSE_EQ|INE061F01013",
    "GAIL":       "NSE_EQ|INE129A01019",
    "GLENMARK":   "NSE_EQ|INE935A01035",
    "GMRINFRA":   "NSE_EQ|INE776C01039",
    "GNFC":       "NSE_EQ|INE113A01013",
    "GODREJCP":   "NSE_EQ|INE102D01028",
    "GODREJPROP": "NSE_EQ|INE484J01027",
    "GRANULES":   "NSE_EQ|INE101D01020",
    "GRASIM":     "NSE_EQ|INE047A01021",
    "GUJGASLTD":  "NSE_EQ|INE844O01030",
    "HAL":        "NSE_EQ|INE066F01012",
    "HAVELLS":    "NSE_EQ|INE176B01034",
    "HCLTECH":    "NSE_EQ|INE860A01027",
    "HDFCAMC":    "NSE_EQ|INE127D01025",
    "HDFCBANK":   "NSE_EQ|INE040A01034",
    "HDFCLIFE":   "NSE_EQ|INE795G01014",
    "HEROMOTOCO": "NSE_EQ|INE158A01026",
    "HFCL":       "NSE_EQ|INE548A01028",
    "HINDALCO":   "NSE_EQ|INE038A01020",
    "HINDCOPPER": "NSE_EQ|INE531E01026",
    "HINDPETRO":  "NSE_EQ|INE094A01015",
    "HINDUNILVR": "NSE_EQ|INE030A01027",
    "HONASA":     "NSE_EQ|INE343K01035",
    "ICICIBANK":  "NSE_EQ|INE090A01021",
    "ICICIGI":    "NSE_EQ|INE765G01017",
    "ICICIPRULI": "NSE_EQ|INE726G01019",
    "IDEA":       "NSE_EQ|INE669E01016",
    "IDFC":       "NSE_EQ|INE043D01016",
    "IDFCFIRSTB": "NSE_EQ|INE818V01030",
    "IEX":        "NSE_EQ|INE022Q01020",
    "IGL":        "NSE_EQ|INE203G01027",
    "INDHOTEL":   "NSE_EQ|INE053A01029",
    "INDIACEM":   "NSE_EQ|INE383A01012",
    "INDIAMART":  "NSE_EQ|INE493T01026",
    "INDIANB":    "NSE_EQ|INE562A01011",
    "INDIGO":     "NSE_EQ|INE646L01027",
    "INDUSINDBK": "NSE_EQ|INE095A01012",
    "INDUSTOWER": "NSE_EQ|INE121J01017",
    "INFY":       "NSE_EQ|INE009A01021",
    "INTELLECT":  "NSE_EQ|INE306R01017",
    "IOC":        "NSE_EQ|INE242A01010",
    "IPCALAB":    "NSE_EQ|INE571A01020",
    "IRCTC":      "NSE_EQ|INE335Y01020",
    "IRFC":       "NSE_EQ|INE053F01010",
    "ITC":        "NSE_EQ|INE154A01025",
    "JINDALSTEL": "NSE_EQ|INE749A01030",
    "JIOFIN":     "NSE_EQ|INE758T01015",
    "JSL":        "NSE_EQ|INE 205A01025",
    "JSWENERGY":  "NSE_EQ|INE121E01018",
    "JSWSTEEL":   "NSE_EQ|INE019A01038",
    "JUBLFOOD":   "NSE_EQ|INE797F01020",
    "KALYANKJIL": "NSE_EQ|INE303R01014",
    "KEI":        "NSE_EQ|INE878B01027",
    "KOTAKBANK":  "NSE_EQ|INE237A01028",
    "KPITTECH":   "NSE_EQ|INE618Z01016",
    "LALPATHLAB": "NSE_EQ|INE093I01010",
    "LAURUSLABS":  "NSE_EQ|INE947Q01028",
    "LICHSGFIN":  "NSE_EQ|INE115A01026",
    "LICI":       "NSE_EQ|INE0J1Y01017",
    "LINDEINDIA": "NSE_EQ|INE663A01017",
    "LT":         "NSE_EQ|INE018A01030",
    "LTIM":       "NSE_EQ|INE214T01019",
    "LTTS":       "NSE_EQ|INE010V01017",
    "LUPIN":      "NSE_EQ|INE326A01037",
    "M&M":        "NSE_EQ|INE101A01026",
    "M&MFIN":     "NSE_EQ|INE774D01024",
    "MANAPPURAM": "NSE_EQ|INE522D01027",
    "MARICO":     "NSE_EQ|INE196A01026",
    "MARUTI":     "NSE_EQ|INE585B01010",
    "MCXINDIA":   "NSE_EQ|INE745G01035",
    "METROPOLIS": "NSE_EQ|INE112L01020",
    "MFSL":       "NSE_EQ|INE582A01016",
    "MGL":        "NSE_EQ|INE562M01019",
    "MOTHERSON":  "NSE_EQ|INE775A01035",
    "MPHASIS":    "NSE_EQ|INE356A01018",
    "MRF":        "NSE_EQ|INE883A01011",
    "MUTHOOTFIN": "NSE_EQ|INE414G01012",
    "NAM-INDIA":  "NSE_EQ|INE583K01012",
    "NATIONALUM": "NSE_EQ|INE139A01034",
    "NAUKRI":     "NSE_EQ|INE663F01024",
    "NAVINFLUOR": "NSE_EQ|INE048G01026",
    "NESTLEIND":  "NSE_EQ|INE239A01016",
    "NHPC":       "NSE_EQ|INE848E01016",
    "NMDC":       "NSE_EQ|INE584A01023",
    "NTPC":       "NSE_EQ|INE733E01010",
    "NYKAA":      "NSE_EQ|INE388Y01029",
    "OBEROIRLTY": "NSE_EQ|INE093I01010",
    "OFSS":       "NSE_EQ|INE881D01027",
    "OIL":        "NSE_EQ|INE274J01014",
    "ONGC":       "NSE_EQ|INE213A01029",
    "PAGEIND":    "NSE_EQ|INE761H01022",
    "PATANJALI":  "NSE_EQ|INE623Z01017",
    "PEL":        "NSE_EQ|INE140A01024",
    "PERSISTENT": "NSE_EQ|INE262H01021",
    "PETRONET":   "NSE_EQ|INE347G01014",
    "PFC":        "NSE_EQ|INE134E01011",
    "PIDILITIND": "NSE_EQ|INE318A01026",
    "PIIND":      "NSE_EQ|INE603J01030",
    "PNB":        "NSE_EQ|INE160A01022",
    "POLICYBZR":  "NSE_EQ|INE417T01026",
    "POLYCAB":    "NSE_EQ|INE455K01017",
    "POWERGRID":  "NSE_EQ|INE752E01010",
    "PVRINOX":    "NSE_EQ|INE191H01036",
    "RAMCOCEM":   "NSE_EQ|INE331A01037",
    "RBLBANK":    "NSE_EQ|INE976G01028",
    "RECLTD":     "NSE_EQ|INE020B01018",
    "RELIANCE":   "NSE_EQ|INE002A01018",
    "SAIL":       "NSE_EQ|INE114A01011",
    "SBICARD":    "NSE_EQ|INE018E01016",
    "SBILIFE":    "NSE_EQ|INE123W01016",
    "SBIN":       "NSE_EQ|INE062A01020",
    "SHREECEM":   "NSE_EQ|INE070A01015",
    "SHRIRAMFIN": "NSE_EQ|INE721A01013",
    "SIEMENS":    "NSE_EQ|INE003A01024",
    "SOBHA":      "NSE_EQ|INE671H01015",
    "SOLARINDS":  "NSE_EQ|INE343H01029",
    "SRF":        "NSE_EQ|INE647A01010",
    "SUNTV":      "NSE_EQ|INE424H01027",
    "SUNPHARMA":  "NSE_EQ|INE044A01036",
    "SUPREMEIND": "NSE_EQ|INE195A01028",
    "SYNGENE":    "NSE_EQ|INE398R01022",
    "TATACHEM":   "NSE_EQ|INE092A01019",
    "TATACOMM":   "NSE_EQ|INE151A01013",
    "TATACONSUM": "NSE_EQ|INE192A01025",
    "TATAELXSI":  "NSE_EQ|INE670A01012",
    "TATAMOTORS": "NSE_EQ|INE155A01022",
    "TATAPOWER":  "NSE_EQ|INE245A01021",
    "TATASTEEL":  "NSE_EQ|INE081A01020",
    "TCS":        "NSE_EQ|INE467B01029",
    "TECHM":      "NSE_EQ|INE669C01036",
    "TITAN":      "NSE_EQ|INE280A01028",
    "TORNTPHARM": "NSE_EQ|INE685A01028",
    "TORNTPOWER": "NSE_EQ|INE813H01021",
    "TRENT":      "NSE_EQ|INE849A01020",
    "TVSMOTOR":   "NSE_EQ|INE494B01023",
    "UBL":        "NSE_EQ|INE686F01025",
    "UJJIVAN":    "NSE_EQ|INE334L01012",
    "ULTRACEMCO": "NSE_EQ|INE481G01011",
    "UNIONBANK":  "NSE_EQ|INE692A01016",
    "UPL":        "NSE_EQ|INE628A01036",
    "VEDL":       "NSE_EQ|INE205A01025",
    "VOLTAS":     "NSE_EQ|INE226A01021",
    "WHIRLPOOL":  "NSE_EQ|INE716A01013",
    "WIPRO":      "NSE_EQ|INE075A01022",
    "YESBANK":    "NSE_EQ|INE528G01035",
    "ZEEL":       "NSE_EQ|INE256A01028",
    "ZOMATO":     "NSE_EQ|INE758T01015",
    "NYKAA":      "NSE_EQ|INE388Y01029",
    "SUZLON":     "NSE_EQ|INE040H01021",
    "ZYDUSLIFE":  "NSE_EQ|INE010B01027",
}

# ── TIMEFRAME CONFIG ──────────────────────────────────────
TF = {
    "monthly": {"interval": "month",     "days": 1825},
    "weekly":  {"interval": "week",      "days": 730},
    "daily":   {"interval": "day",       "days": 400},
    "tf75":    {"interval": "30minute",  "days": 60},
    "tf15":    {"interval": "30minute",  "days": 30},
    "tf5":     {"interval": "1minute",   "days": 5},
}

DEFAULT_SCRIPS = [
    "NIFTY","BANKNIFTY","RELIANCE","TCS","HDFCBANK",
    "INFY","SBIN","ICICIBANK","AXISBANK","TATAMOTORS",
    "BAJFINANCE","KOTAKBANK","LT","WIPRO","HINDUNILVR"
]

# ── CACHE ─────────────────────────────────────────────────

# DYNAMIC INSTRUMENT LOOKUP
_instrument_map    = {}
_instrument_loaded = False
INSTRUMENT_FILE    = "nse_instruments.json"

def load_instrument_file():
    global _instrument_map, _instrument_loaded
    try:
        if os.path.exists(INSTRUMENT_FILE):
            age = time.time() - os.path.getmtime(INSTRUMENT_FILE)
            if age < 86400:
                with open(INSTRUMENT_FILE) as f:
                    _instrument_map = json.load(f)
                log.info(f"Instruments loaded from cache: {len(_instrument_map)} symbols")
                _instrument_loaded = True
                return
        log.info("Downloading Upstox NSE instruments...")
        r = requests.get(
            "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
            timeout=30
        )
        if r.status_code == 200:
            import gzip, io
            with gzip.open(io.BytesIO(r.content)) as f:
                instruments = json.load(f)
            mp = {}
            for inst in instruments:
                if inst.get("instrument_type") == "EQ" and inst.get("segment") == "NSE_EQ":
                    sym  = inst.get("trading_symbol", "").upper()
                    ikey = inst.get("instrument_key", "")
                    if sym and ikey:
                        mp[sym] = ikey
            _instrument_map = mp
            with open(INSTRUMENT_FILE, 'w') as f:
                json.dump(mp, f)
            log.info(f"Downloaded {len(mp)} NSE EQ instruments")
            _instrument_loaded = True
        else:
            log.warning(f"Instrument download failed: {r.status_code}")
    except Exception as e:
        log.error(f"Instrument load error: {e}")

def resolve_instrument(ticker):
    ticker = ticker.upper().strip()
    if ticker in INSTRUMENTS:
        return INSTRUMENTS[ticker]
    if ticker in _instrument_map:
        return _instrument_map[ticker]
    return None

_cache    = {}
_cache_ts = {}
CACHE_TTL = 300  # 5 min

# ── UPSTOX FETCH ──────────────────────────────────────────
def fetch_candles(instrument_key, interval, days):
    token = get_token()
    if not token:
        return None, "no_token"

    key = f"{instrument_key}_{interval}"
    now = time.time()
    if key in _cache and (now - _cache_ts.get(key, 0)) < CACHE_TTL:
        return _cache[key], None

    try:
        to_dt   = date.today()
        from_dt = to_dt - timedelta(days=days)
        url = (
            f"https://api.upstox.com/v2/historical-candle"
            f"/{requests.utils.quote(instrument_key, safe='')}"
            f"/{interval}"
            f"/{to_dt.isoformat()}"
            f"/{from_dt.isoformat()}"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            candles = r.json().get("data", {}).get("candles", [])
            if not candles:
                return None, "no_data"
            closes = [c[4] for c in candles]
            _cache[key]    = closes
            _cache_ts[key] = now
            return closes, None
        else:
            log.warning(f"Upstox {instrument_key}: {r.status_code} {r.text[:120]}")
            return None, f"http_{r.status_code}"
    except Exception as e:
        log.warning(f"Fetch error {instrument_key}: {e}")
        return None, str(e)

# ── MACD ──────────────────────────────────────────────────
def calc_macd(closes, fast=12, slow=26, sig=9):
    if not closes or len(closes) < slow + sig + 2:
        return None
    s  = pd.Series(closes)
    ml = s.ewm(span=fast, adjust=False).mean() - s.ewm(span=slow, adjust=False).mean()
    sl = ml.ewm(span=sig,  adjust=False).mean()
    hi = ml - sl
    cv, pv = float(ml.iloc[-1]), float(ml.iloc[-2])
    cz = "ABOVE" if cv > 0 else "BELOW"
    pz = "ABOVE" if pv > 0 else "BELOW"
    return {
        "signal":    "BUY" if cz == "ABOVE" else "SELL",
        "zero":      cz,
        "crossover": cz != pz,
        "histogram": round(float(hi.iloc[-1]), 6),
        "macd":      round(cv, 6),
    }

EMPTY_SIG = {"signal": "—", "zero": "—", "crossover": False, "histogram": 0}

def get_signals(ticker, timeframes):
    ticker = ticker.upper().strip()
    ikey   = resolve_instrument(ticker)
    result = {"symbol": ticker, "timeframes": {}, "timestamp": datetime.utcnow().isoformat()}

    if not ikey:
        for tf in timeframes:
            result["timeframes"][tf] = {**EMPTY_SIG, "error": "symbol_not_mapped"}
        return result

    result["instrument_key"] = ikey
    for tf in timeframes:
        cfg = TF.get(tf)
        if not cfg:
            result["timeframes"][tf] = EMPTY_SIG
            continue
        closes, err = fetch_candles(ikey, cfg["interval"], cfg["days"])
        if err == "no_token":
            result["timeframes"][tf] = {**EMPTY_SIG, "error": "upstox_not_connected"}
            continue
        if not closes or len(closes) < 35:
            result["timeframes"][tf] = {**EMPTY_SIG, "error": err or "insufficient_data"}
            continue
        sig = calc_macd(closes)
        result["timeframes"][tf] = sig if sig else EMPTY_SIG

    return result

# ── ELLIOTT WAVE PATTERN DETECTION ────────────────────────
def detect_ew_pattern(closes):
    if not closes or len(closes) < 50:
        return {"pattern": "Insufficient Data", "wave": "—", "confidence": 0}

    prices = closes[-50:]
    n = len(prices)

    highs, lows = [], []
    for i in range(2, n-2):
        if prices[i] > prices[i-1] and prices[i] > prices[i+1] and prices[i] > prices[i-2] and prices[i] > prices[i+2]:
            highs.append((i, prices[i]))
        if prices[i] < prices[i-1] and prices[i] < prices[i+1] and prices[i] < prices[i-2] and prices[i] < prices[i+2]:
            lows.append((i, prices[i]))

    curr = prices[-1]
    start = prices[0]
    trend_pct = (curr - start) / start * 100

    if len(highs) >= 2 and len(lows) >= 2:
        last_high = highs[-1][1]
        last_low  = lows[-1][1]
        prev_high = highs[-2][1] if len(highs) >= 2 else last_high
        prev_low  = lows[-2][1]  if len(lows)  >= 2 else last_low

        if last_high > prev_high and last_low > prev_low and trend_pct > 2:
            if trend_pct > 8:
                return {"pattern": "Impulse 5-Wave",  "wave": "Wave 3", "confidence": 85, "bias": "bullish"}
            return     {"pattern": "Wave 3 Breakout", "wave": "Wave 3", "confidence": 78, "bias": "bullish"}

        if last_high < prev_high and last_low < prev_low and trend_pct < -2:
            return     {"pattern": "ABC Correction",  "wave": "Wave C",  "confidence": 74, "bias": "bearish"}

        if abs(trend_pct) < 2:
            return     {"pattern": "Triangle Pattern", "wave": "Wave 4", "confidence": 65, "bias": "neutral"}

        if last_high > prev_high and last_low < prev_low:
            return     {"pattern": "Ending Diagonal",  "wave": "Wave 5", "confidence": 70, "bias": "bearish"}

    if trend_pct > 5:
        return {"pattern": "Impulse 5-Wave",  "wave": "Wave 3", "confidence": 72, "bias": "bullish"}
    if trend_pct < -5:
        return {"pattern": "ABC Correction",  "wave": "Wave A",  "confidence": 68, "bias": "bearish"}
    return     {"pattern": "Consolidation",   "wave": "Wave 4", "confidence": 60, "bias": "neutral"}

def get_ltp(instrument_key):
    token = get_token()
    if not token:
        return None
    try:
        r = requests.get(
            "https://api.upstox.com/v2/market-quote/ltp",
            params={"instrument_key": instrument_key},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=8
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            for k, v in data.items():
                return v.get("last_price")
    except:
        pass
    return None

def scan_ticker(ticker):
    ikey = resolve_instrument(ticker.upper())
    if not ikey:
        return None

    closes, err = fetch_candles(ikey, "day", 200)
    if not closes:
        return None

    ew      = detect_ew_pattern(closes)
    macd    = calc_macd(closes) or EMPTY_SIG
    ltp     = get_ltp(ikey)

    chg_pct = 0
    if len(closes) >= 2:
        chg_pct = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2)

    return {
        "symbol":     ticker.upper(),
        "pattern":    ew["pattern"],
        "wave":       ew["wave"],
        "confidence": ew["confidence"],
        "bias":       ew.get("bias", "neutral"),
        "signal":     macd["signal"],
        "price":      ltp or closes[-1],
        "change_pct": chg_pct,
        "timeframe":  "1D",
        "timestamp":  datetime.utcnow().isoformat(),
    }

# ── BLOG ──────────────────────────────────────────────────
def load_posts():
    try:
        with open(POSTS_FILE) as f: return json.load(f)
    except: return []

def save_posts(posts):
    try:
        with open(POSTS_FILE, 'w') as f: json.dump(posts[:100], f, indent=2)
    except: pass

# ── HELPERS ───────────────────────────────────────────────
def _safe_int(val):
    try:
        return int(str(val).replace(",", "").strip() or 0)
    except:
        return 0

def _html_page(title, msg, color, link, link_text):
    c = "#00ff88" if color == "green" else "#ff1744"
    bc= "rgba(0,255,136,.06)" if color=="green" else "rgba(255,23,68,.06)"
    return f"""<!DOCTYPE html><html><head><meta charset=UTF-8>
    <meta name=viewport content="width=device-width,initial-scale=1">
    <title>{title} | WaveEdge</title>
    <style>*{{box-sizing:border-box;margin:0;padding:0}}
    body{{background:#020c14;color:#dff0f8;font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}}
    .box{{background:#061525;border:2px solid {c};border-radius:16px;padding:48px 40px;text-align:center;max-width:440px;width:100%;background:{bc}}}
    h1{{font-size:28px;margin-bottom:14px;color:{c}}}
    p{{color:#4d8099;font-size:15px;line-height:1.7;margin-bottom:28px}}
    a{{display:inline-block;background:{c};color:#000;padding:13px 32px;border-radius:8px;text-decoration:none;font-weight:700;font-size:15px}}
    </style></head><body>
    <div class=box><h1>{title}</h1><p>{msg}</p><a href="{link}">{link_text}</a></div>
    </body></html>"""

# ── BACKGROUND THREADS ────────────────────────────────────
def bg_warm_cache():
    time.sleep(20)
    while True:
        if get_token():
            log.info("Warming cache for default scrips...")
            for t in DEFAULT_SCRIPS:
                try:
                    get_signals(t, ["monthly", "weekly", "daily"])
                    time.sleep(1)
                except: pass
            log.info("Cache warm done.")
        else:
            log.warning("No Upstox token — skipping cache warm. Please reconnect.")
        time.sleep(600)

def bg_keep_alive():
    time.sleep(60)
    while True:
        try:
            requests.get(f"{SELF_URL}/health", timeout=10)
            log.info("Keep-alive ping sent")
        except: pass
        time.sleep(600)

# ══════════════════════════════════════════════════════════
# ── ROUTES ────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════

@app.route("/")
def index():
    token = get_token()
    login_url = (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}&scope=historical_data"
    )
    return jsonify({
        "name":        "WaveEdge API — Upstox Edition",
        "version":     "5.1",
        "connected":   bool(token),
        "login_url":   login_url if not token else "already_connected",
        "endpoints": {
            "/health":           "Status check",
            "/upstox/login":     "Redirect to Upstox login",
            "/upstox/callback":  "OAuth callback (auto)",
            "/upstox/status":    "Token status",
            "/macd/<ticker>":    "MACD signals for one ticker",
            "/macd/batch":       "MACD for multiple tickers",
            "/scan":             "Elliott Wave scanner results",
            "/scan/<ticker>":    "Scan single ticker",
            "/symbols":          "List all mapped symbols",
            "/blog":             "Blog posts",
            "/fii":              "FII/DII participant OI data",
            "/pcr":              "Nifty Put/Call Ratio",
        }
    })

@app.route("/health")
def health():
    return jsonify({
        "status":    "ok",
        "connected": bool(get_token()),
        "time":      datetime.utcnow().isoformat(),
        "cached":    len(_cache),
    })

# ── UPSTOX AUTH ───────────────────────────────────────────
@app.route("/upstox/token", methods=["GET","POST"])
def manual_token():
    if request.method == "POST":
        data  = request.get_json() or {}
        token = data.get("access_token","").strip()
        key   = data.get("admin_key","")
        if key != ADMIN_KEY:
            return jsonify({"error":"unauthorized"}), 401
        if not token:
            return jsonify({"error":"access_token required"}), 400
        save_token({"access_token": token, "expires_at": date.today().isoformat()})
        return jsonify({"success": True, "message": "Token saved!"})

    return """<!DOCTYPE html><html><head><meta charset=UTF-8>
    <title>Set Upstox Token | WaveEdge</title>
    <style>*{box-sizing:border-box;margin:0;padding:0}body{background:#020c14;color:#dff0f8;font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}.box{background:#061525;border:1px solid #00e5ff;border-radius:14px;padding:36px;width:100%;max-width:500px}h2{color:#00e5ff;margin-bottom:8px}p{color:#4d8099;font-size:13px;margin-bottom:20px;line-height:1.6}label{display:block;font-size:11px;color:#4d8099;letter-spacing:1px;margin-bottom:5px;text-transform:uppercase}input,textarea{width:100%;background:#0a1f30;border:1px solid #173348;color:#dff0f8;padding:11px;border-radius:7px;font-size:13px;margin-bottom:14px;font-family:monospace}button{width:100%;background:linear-gradient(135deg,#00e5ff,#00ff88);color:#000;border:none;padding:13px;border-radius:7px;font-weight:700;font-size:15px;cursor:pointer}#msg{margin-top:12px;text-align:center;font-size:13px}</style>
    </head><body><div class=box>
    <h2>&#9889; Set Upstox Access Token</h2>
    <p>Go to <b>account.upstox.com/developer/apps</b> → your app → click <b>Generate</b> next to Access Token → copy and paste below.</p>
    <label>Access Token</label>
    <textarea id=tok rows=4 placeholder="Paste your Upstox access token here..."></textarea>
    <label>Admin Key</label>
    <input id=key type=password placeholder="waveedge2024"/>
    <button onclick=save()>Save Token &#8594;</button>
    <div id=msg></div>
    </div>
    <script>
    async function save(){
      var tok=document.getElementById('tok').value.trim();
      var key=document.getElementById('key').value.trim();
      if(!tok){document.getElementById('msg').innerHTML='<span style=color:#ff1744>Paste your token first</span>';return;}
      var r=await fetch('/upstox/token',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({access_token:tok,admin_key:key})});
      var d=await r.json();
      if(d.success){document.getElementById('msg').innerHTML='<span style=color:#00ff88>&#10004; Token saved! <a href=/ style=color:#00e5ff>Go to API</a></span>';}
      else{document.getElementById('msg').innerHTML='<span style=color:#ff1744>Error: '+d.error+'</span>';}
    }
    </script></body></html>"""

@app.route("/upstox/login")
def upstox_login():
    login_url = (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}&scope=historical_data"
    )
    return redirect(login_url)

@app.route("/upstox/callback")
def upstox_callback():
    code  = request.args.get("code")
    error = request.args.get("error")

    if error:
        return _html_page("❌ Login Error", f"Error: {error}", "red", "/upstox/login", "Try Again"), 400
    if not code:
        return _html_page("❌ No Code", "No auth code received from Upstox.", "red", "/upstox/login", "Try Again"), 400

    ok, err = exchange_code(code)
    if ok:
        return _html_page(
            "✅ Upstox Connected!",
            "Real-time NSE data is now live on WaveEdge.<br>Token refreshes daily — click Reconnect each morning.",
            "green", "https://waveedge.in", "Go to WaveEdge →"
        )
    debug_info = f"""
    Error: {err}<br><br>
    Client ID: {CLIENT_ID[:8]}...{CLIENT_ID[-4:]}<br>
    Secret set: {'YES (' + CLIENT_SECRET[:3] + '...)' if CLIENT_SECRET else 'NO - MISSING!'}<br>
    Redirect URI: {REDIRECT_URI}<br>
    Code received: {code[:8]}...<br>
    """
    return _html_page(
        "❌ Token Exchange Failed",
        f"Upstox rejected the token request.<br><br><small style='text-align:left;display:block;background:#0a1f30;padding:12px;border-radius:6px;font-family:monospace;font-size:11px;line-height:1.8'>{debug_info}</small>",
        "red", "/upstox/login", "Try Again"
    ), 400

@app.route("/upstox/status")
def upstox_status():
    token = get_token()
    login_url = (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}&scope=historical_data"
    )
    return jsonify({
        "connected":  bool(token),
        "expires_at": _tok.get("expires_at", ""),
        "login_url":  login_url,
    })

# ── MACD ROUTES ───────────────────────────────────────────
@app.route("/macd/<ticker>")
def macd_single(ticker):
    paid = request.args.get("paid", "false").lower() == "true"
    tf_p = request.args.get("tf", "")
    if tf_p:   tfs = [t.strip() for t in tf_p.split(",") if t.strip() in TF]
    elif paid: tfs = list(TF.keys())
    else:      tfs = ["monthly", "weekly", "daily"]
    return jsonify(get_signals(ticker, tfs))

@app.route("/macd/batch", methods=["GET", "POST"])
def macd_batch():
    if request.method == "POST":
        data   = request.get_json() or {}
        scrips = data.get("scrips", DEFAULT_SCRIPS)
        paid   = data.get("paid", False)
        tf_p   = data.get("timeframes", None)
    else:
        scrips = [s.strip() for s in request.args.get("scrips", ",".join(DEFAULT_SCRIPS)).split(",") if s.strip()]
        paid   = request.args.get("paid", "false").lower() == "true"
        tf_p   = request.args.get("tf", None)

    scrips = scrips[:20]
    if tf_p:   timeframes = [t.strip() for t in tf_p.split(",") if t.strip() in TF]
    elif paid: timeframes = list(TF.keys())
    else:      timeframes = ["monthly", "weekly", "daily"]

    results = {}
    for ticker in scrips:
        try:
            results[ticker] = get_signals(ticker, timeframes)
            time.sleep(0.4)
        except Exception as e:
            results[ticker] = {"error": str(e), "symbol": ticker}

    return jsonify({
        "count":      len(results),
        "timeframes": timeframes,
        "connected":  bool(get_token()),
        "timestamp":  datetime.utcnow().isoformat(),
        "results":    results,
    })

# ── SCANNER ROUTES ────────────────────────────────────────
_scan_cache     = []
_scan_cache_ts  = 0
SCAN_CACHE_TTL  = 300

@app.route("/scan")
def scan_all():
    global _scan_cache, _scan_cache_ts
    force = request.args.get("force", "false").lower() == "true"

    if not force and _scan_cache and (time.time() - _scan_cache_ts) < SCAN_CACHE_TTL:
        return jsonify({"count": len(_scan_cache), "cached": True, "results": _scan_cache})

    if not get_token():
        return jsonify({"error": "upstox_not_connected", "message": "Please reconnect Upstox at /upstox/login"}), 401

    results = []
    for ticker in DEFAULT_SCRIPS:
        try:
            r = scan_ticker(ticker)
            if r: results.append(r)
            time.sleep(0.8)
        except Exception as e:
            log.warning(f"Scan error {ticker}: {e}")

    _scan_cache    = results
    _scan_cache_ts = time.time()

    return jsonify({
        "count":     len(results),
        "cached":    False,
        "timestamp": datetime.utcnow().isoformat(),
        "results":   results,
    })

@app.route("/scan/<ticker>")
def scan_single(ticker):
    if not get_token():
        return jsonify({"error": "upstox_not_connected"}), 401
    result = scan_ticker(ticker)
    if not result:
        return jsonify({"error": f"{ticker} not found or no data"}), 404
    return jsonify(result)

# ── BLOG ROUTES ───────────────────────────────────────────
@app.route("/blog")
def blog():
    posts = load_posts()
    cat   = request.args.get("cat", "all")
    if cat != "all":
        posts = [p for p in posts if p.get("cat") == cat]
    return jsonify({"count": len(posts), "posts": posts[:50]})

@app.route("/blog/post", methods=["POST"])
def blog_post():
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json() or {}
    posts = load_posts()
    data["id"]   = int(time.time() * 1000)
    data["date"] = datetime.utcnow().isoformat()
    posts.insert(0, data)
    save_posts(posts)
    return jsonify({"success": True, "id": data["id"]})

# ── SYMBOLS ───────────────────────────────────────────────
@app.route("/symbols")
def symbols():
    return jsonify({
        "count":   len(INSTRUMENTS),
        "symbols": list(INSTRUMENTS.keys()),
    })

# ── FII / DII DATA ────────────────────────────────────────
@app.route("/fii")
def fii_data():
    """
    FII/DII participant OI data.
    Source 1: NSE public archive CSV (published ~6pm daily, no auth needed).
    Source 2: Upstox for Nifty spot price.
    Falls back to spot-only if CSV not yet published (before 6pm).
    """
    result = {
        "data": [],
        "spotPrice": 0, "spotChange": 0, "spotPct": 0,
        "pcr": 0, "source": "unknown", "dataDate": ""
    }

    # 1. Nifty spot from Upstox
    token = get_token()
    if token:
        try:
            sr = requests.get(
                "https://api.upstox.com/v2/market-quote/ltp",
                params={"instrument_key": "NSE_INDEX|Nifty 50"},
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=5
            )
            if sr.status_code == 200:
                ltp = sr.json().get("data", {}).get("NSE_INDEX:Nifty 50", {}).get("last_price", 0)
                result["spotPrice"] = ltp
                result["source"] = "upstox_spot"
        except Exception as e:
            log.warning(f"Upstox spot error: {e}")

    # 2. Participant OI from NSE public archive CSV
    csv_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "text/csv,*/*",
    }

    participant_data = []
    for days_back in range(0, 8):
        check_date = datetime.now() - timedelta(days=days_back)
        if check_date.weekday() >= 5:
            continue
        date_str = check_date.strftime("%d%m%Y")
        year_str = check_date.strftime("%Y")
        mon_str  = check_date.strftime("%b").upper()
        csv_url  = f"https://archives.nseindia.com/content/historical/DERIVATIVES/{year_str}/{mon_str}/fao_participant_oi_{date_str}.csv"

        try:
            r = requests.get(csv_url, headers=csv_headers, timeout=10)
            if r.status_code == 200 and "Client" in r.text:
                import csv, io
                reader = csv.DictReader(io.StringIO(r.text))
                rows = list(reader)
                if rows:
                    participant_data = rows
                    result["dataDate"] = check_date.strftime("%d-%b-%Y")
                    result["source"]   = "nse_csv"
                    log.info(f"FII CSV loaded for {result['dataDate']}")
                    break
        except Exception as e:
            log.warning(f"CSV fetch error for {date_str}: {e}")
            continue

    if participant_data:
        mapped = []
        for row in participant_data:
            ct = row.get("Client Type", "").strip()
            if not ct or ct.lower() == "total":
                continue
            mapped.append({
                "clientType":          ct,
                "instrumentType":      "Index Futures",
                "longQuantity":        _safe_int(row.get("Future Index Long", 0)),
                "shortQuantity":       _safe_int(row.get("Future Index Short", 0)),
                "changeLongQuantity":  _safe_int(row.get("Future Index Long Change", 0)),
                "changeShortQuantity": _safe_int(row.get("Future Index Short Change", 0)),
            })
            mapped.append({
                "clientType":          ct,
                "instrumentType":      "Index Calls",
                "longQuantity":        _safe_int(row.get("Option Index Call Long", 0)),
                "shortQuantity":       _safe_int(row.get("Option Index Call Short", 0)),
                "changeLongQuantity":  _safe_int(row.get("Option Index Call Long Change", 0)),
                "changeShortQuantity": _safe_int(row.get("Option Index Call Short Change", 0)),
            })
            mapped.append({
                "clientType":          ct,
                "instrumentType":      "Index Puts",
                "longQuantity":        _safe_int(row.get("Option Index Put Long", 0)),
                "shortQuantity":       _safe_int(row.get("Option Index Put Short", 0)),
                "changeLongQuantity":  _safe_int(row.get("Option Index Put Long Change", 0)),
                "changeShortQuantity": _safe_int(row.get("Option Index Put Short Change", 0)),
            })
            mapped.append({
                "clientType":          ct,
                "instrumentType":      "Stock Futures",
                "longQuantity":        _safe_int(row.get("Future Stock Long", 0)),
                "shortQuantity":       _safe_int(row.get("Future Stock Short", 0)),
                "changeLongQuantity":  _safe_int(row.get("Future Stock Long Change", 0)),
                "changeShortQuantity": _safe_int(row.get("Future Stock Short Change", 0)),
            })

        result["data"] = mapped
        return jsonify(result)

    # All CSV attempts failed
    if result["spotPrice"]:
        result["spotOnly"] = True
        result["error"] = "NSE CSV unavailable — may be holiday or published after 6pm"
        return jsonify(result)

    return jsonify({"error": "All data sources failed"}), 503


@app.route("/pcr")
def pcr_data():
    """Fetch Nifty PCR from NSE option chain."""
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
        })
        session.get("https://www.nseindia.com", timeout=8)
        r = session.get(
            "https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",
            headers={"Referer": "https://www.nseindia.com/option-chain"},
            timeout=10
        )
        r.raise_for_status()
        data     = r.json()
        filtered = data.get("filtered", {})
        pe_oi    = filtered.get("PE", {}).get("totOI", 0)
        ce_oi    = filtered.get("CE", {}).get("totOI", 1)
        pcr      = round(pe_oi / max(ce_oi, 1), 4)
        return jsonify({"pcr": pcr, "pe_oi": pe_oi, "ce_oi": ce_oi})
    except Exception as e:
        return jsonify({"error": str(e)}), 503



# ── TOTP AUTO TOKEN REFRESH ───────────────────────────────
UPSTOX_USERNAME  = os.environ.get("UPSTOX_USERNAME", "")
UPSTOX_PIN       = os.environ.get("UPSTOX_PIN", "")
UPSTOX_TOTP_SECRET = os.environ.get("UPSTOX_TOTP_SECRET", "")

def generate_totp():
    """Generate current TOTP code from secret (supports Base32 and Base64)."""
    try:
        import hmac, hashlib, base64, struct
        secret = UPSTOX_TOTP_SECRET.strip()
        # Try Base32 first (standard TOTP)
        try:
            b32 = secret.upper().replace(" ", "")
            missing = len(b32) % 8
            if missing: b32 += '=' * (8 - missing)
            key = base64.b32decode(b32)
        except Exception:
            # Fall back to Base64 (Upstox format)
            padded = secret + '=' * (4 - len(secret) % 4)
            key = base64.b64decode(padded)
        t = int(time.time()) // 30
        msg = struct.pack('>Q', t)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        offset = h[-1] & 0x0f
        code = struct.unpack('>I', h[offset:offset+4])[0] & 0x7fffffff
        return str(code % 1000000).zfill(6)
    except Exception as e:
        log.error(f"TOTP generation error: {e}")
        return None

def auto_refresh_token():
    """Auto-refresh Upstox token using upstox-totp package."""
    if not all([UPSTOX_USERNAME, UPSTOX_PIN, UPSTOX_TOTP_SECRET, CLIENT_ID, CLIENT_SECRET]):
        log.warning("Auto-refresh: missing credentials in environment")
        return False
    try:
        from upstox_totp import UpstoxTOTP
        from pydantic import SecretStr
        log.info("Auto-refreshing Upstox token via upstox-totp...")
        upx = UpstoxTOTP(
            username=UPSTOX_USERNAME,
            pin_code=SecretStr(UPSTOX_PIN),
            totp_secret=SecretStr(UPSTOX_TOTP_SECRET),
            client_id=CLIENT_ID,
            client_secret=SecretStr(CLIENT_SECRET),
            redirect_uri=REDIRECT_URI,
        )
        response = upx.app_token.get_access_token()
        if response.success and response.data:
            token = response.data.access_token
            save_token({"access_token": token, "expires_at": date.today().isoformat()})
            log.info(f"Auto-refresh successful! User: {response.data.user_name}")
            return True
        log.error(f"Auto-refresh failed: {response.error}")
        return False
    except ImportError:
        log.error("upstox-totp not installed. Add to requirements.txt")
        return False
    except Exception as e:
        log.error(f"Auto-refresh error: {e}")
        return False

def bg_auto_refresh():
    """Background thread: refresh token daily at 8:45am IST."""
    time.sleep(60)  # Wait for startup
    while True:
        try:
            now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
            token_expired = not get_token()
            # Refresh at 8:45am IST or if token is expired
            if token_expired or (now_ist.hour == 8 and now_ist.minute == 45):
                log.info(f"Attempting auto-refresh at {now_ist.strftime('%H:%M')} IST")
                auto_refresh_token()
                time.sleep(120)  # avoid re-triggering
            else:
                time.sleep(30)
        except Exception as e:
            log.error(f"bg_auto_refresh error: {e}")
            time.sleep(60)

@app.route("/upstox/auto-refresh")
def manual_auto_refresh():
    """Manually trigger token auto-refresh."""
    if not all([UPSTOX_USERNAME, UPSTOX_PIN, UPSTOX_TOTP_SECRET]):
        return jsonify({"error": "TOTP credentials not configured in environment"}), 400
    ok = auto_refresh_token()
    return jsonify({"success": ok, "token_valid": bool(get_token())})


# ── WAVE COUNTS ───────────────────────────────────────────
WAVECOUNTS_FILE = "wavecounts.json"

def load_wavecounts():
    try:
        with open(WAVECOUNTS_FILE) as f: return json.load(f)
    except: return []

def save_wavecounts(posts):
    try:
        with open(WAVECOUNTS_FILE, 'w') as f: json.dump(posts[:60], f, indent=2)
    except: pass

@app.route("/wavecounts/latest")
def wavecounts_latest():
    posts = load_wavecounts()
    if not posts:
        return jsonify({"error": "no_data"}), 404
    return jsonify(posts[0])

@app.route("/wavecounts")
def wavecounts_list():
    posts = load_wavecounts()
    limit = int(request.args.get("limit", 10))
    return jsonify({"count": len(posts), "posts": posts[:limit]})

@app.route("/wavecounts/post", methods=["POST"])
def wavecounts_post():
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json() or {}
    posts = load_wavecounts()
    data["id"]   = int(time.time() * 1000)
    data["date"] = datetime.utcnow().isoformat()
    # Replace today's post if already exists
    today = datetime.utcnow().date().isoformat()
    posts = [p for p in posts if not p.get("date","").startswith(today)]
    posts.insert(0, data)
    save_wavecounts(posts)
    log.info(f"Wave count posted for {today}")
    return jsonify({"success": True, "id": data["id"]})

@app.route("/wavecounts/delete/<int:post_id>", methods=["DELETE"])
def wavecounts_delete(post_id):
    if request.headers.get("X-Admin-Key") != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 401
    posts = load_wavecounts()
    posts = [p for p in posts if p.get("id") != post_id]
    save_wavecounts(posts)
    return jsonify({"success": True})

# ── RAZORPAY SUBSCRIPTION ─────────────────────────────────
RAZORPAY_KEY    = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
SUBSCRIPTIONS_FILE = "subscriptions.json"

def load_subscriptions():
    try:
        with open(SUBSCRIPTIONS_FILE) as f: return json.load(f)
    except: return {}

def save_subscriptions(data):
    try:
        with open(SUBSCRIPTIONS_FILE, 'w') as f: json.dump(data, f, indent=2)
    except: pass

def generate_access_code():
    import hashlib, secrets
    return "WE-" + secrets.token_hex(6).upper()

@app.route("/subscription/verify", methods=["POST"])
def verify_subscription():
    """Verify Razorpay payment and generate access code."""
    data = request.get_json() or {}
    payment_id  = data.get("razorpay_payment_id", "")
    order_id    = data.get("razorpay_order_id", "")
    signature   = data.get("razorpay_signature", "")
    plan        = data.get("plan", "professional")
    email       = data.get("email", "")

    if not all([payment_id, order_id, signature]):
        return jsonify({"error": "Missing payment details"}), 400

    # Verify signature
    try:
        import hmac, hashlib
        msg = f"{order_id}|{payment_id}".encode()
        expected = hmac.new(RAZORPAY_SECRET.encode(), msg, hashlib.sha256).hexdigest()
        if expected != signature:
            return jsonify({"error": "Invalid signature"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    # Generate access code
    code = generate_access_code()
    subs = load_subscriptions()
    subs[code] = {
        "payment_id": payment_id,
        "order_id":   order_id,
        "plan":       plan,
        "email":      email,
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
        "active":     True
    }
    save_subscriptions(subs)
    log.info(f"New subscription: {code} plan={plan} email={email}")
    return jsonify({"success": True, "access_code": code, "plan": plan})

@app.route("/subscription/check/<code>")
def check_subscription(code):
    """Check if access code is valid."""
    subs = load_subscriptions()
    sub  = subs.get(code.upper())
    if not sub:
        return jsonify({"valid": False, "error": "Invalid code"}), 404
    if not sub.get("active"):
        return jsonify({"valid": False, "error": "Subscription inactive"}), 403
    # Check expiry
    try:
        exp = datetime.fromisoformat(sub["expires_at"])
        if datetime.utcnow() > exp:
            return jsonify({"valid": False, "error": "Subscription expired"}), 403
    except: pass
    return jsonify({
        "valid":      True,
        "plan":       sub.get("plan"),
        "expires_at": sub.get("expires_at"),
        "email":      sub.get("email", "")
    })

@app.route("/subscription/create-order", methods=["POST"])
def create_order():
    """Create Razorpay order."""
    if not RAZORPAY_KEY or not RAZORPAY_SECRET:
        return jsonify({"error": "Razorpay not configured"}), 400
    data   = request.get_json() or {}
    plan   = data.get("plan", "professional")
    prices = {"starter": 49900, "professional": 99900, "institutional": 199900}  # paise
    amount = prices.get(plan, 99900)
    try:
        r = requests.post(
            "https://api.razorpay.com/v1/orders",
            auth=(RAZORPAY_KEY, RAZORPAY_SECRET),
            json={"amount": amount, "currency": "INR", "receipt": f"WE-{plan}-{int(time.time())}"},
            timeout=10
        )
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/subscription/create-code", methods=["POST"])
def create_code():
    """Admin: manually create access code for a customer."""
    data    = request.get_json() or {}
    key     = data.get("admin_key", "")
    if key != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 401
    email   = data.get("email", "").strip()
    plan    = data.get("plan", "professional")
    payref  = data.get("payment_ref", "manual")
    if not email:
        return jsonify({"error": "email required"}), 400
    days    = 30
    code    = generate_access_code()
    subs    = load_subscriptions()
    subs[code] = {
        "payment_id":  payref,
        "order_id":    f"manual-{int(time.time())}",
        "plan":        plan,
        "email":       email,
        "created_at":  datetime.utcnow().isoformat(),
        "expires_at":  (datetime.utcnow() + timedelta(days=days)).isoformat(),
        "active":      True
    }
    save_subscriptions(subs)
    log.info(f"Manual code created: {code} plan={plan} email={email}")
    return jsonify({
        "success":     True,
        "access_code": code,
        "plan":        plan,
        "expires_at":  subs[code]["expires_at"]
    })

@app.route("/subscription/admin")
def admin_subscriptions():
    """Admin view of all subscriptions."""
    if request.args.get("key") != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 401
    subs = load_subscriptions()
    return jsonify({"count": len(subs), "subscriptions": subs})

# ── STARTUP ───────────────────────────────────────────────
load_token()
# Auto-refresh token at startup if not valid
if not get_token():
    log.info("No valid token at startup - attempting auto-refresh...")
    threading.Thread(target=auto_refresh_token, daemon=True).start()
threading.Thread(target=load_instrument_file, daemon=True).start()
threading.Thread(target=bg_warm_cache, daemon=True).start()
threading.Thread(target=bg_keep_alive, daemon=True).start()
threading.Thread(target=bg_auto_refresh, daemon=True).start()
log.info("=" * 50)
log.info("WaveEdge API v5.1 — Upstox Edition")
log.info(f"Token valid: {bool(get_token())}")
if not get_token():
    log.info(f"LOGIN URL: {SELF_URL}/upstox/login")
log.info("=" * 50)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
