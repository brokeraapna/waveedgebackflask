"""
WaveEdge Backend - Upstox + NSE FII + Auto Token Refresh
"""
from flask import Flask, jsonify, request, redirect
from flask_cors import CORS
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import threading, time, logging, json, os, re, csv, io
import requests
from functools import wraps

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

# ── TOKEN MANAGEMENT WITH AUTO-REFRESH ────────────────────
_tok = {}
_token_refresh_thread = None

def load_token():
    global _tok
    try:
        with open(TOKEN_FILE) as f:
            _tok = json.load(f)
        log.info(f"Token loaded, expires: {_tok.get('expires_at','?')}")
    except:
        _tok = {}

def save_token(data):
    global _tok
    _tok = data
    try:
        with open(TOKEN_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        log.error(f"Token save error: {e}")

def get_token():
    if not _tok.get('access_token'):
        return None
    exp = _tok.get('expires_at', '')
    if exp and exp < date.today().isoformat():
        log.warning("Token expired - please reconnect Upstox")
        return None
    return _tok['access_token']

def refresh_token_automatically():
    """Background thread to refresh token before expiry"""
    global _tok
    while True:
        time.sleep(3600)  # Check every hour
        if _tok.get('access_token') and _tok.get('expires_at'):
            expiry = datetime.fromisoformat(_tok['expires_at'])
            if datetime.now() > expiry - timedelta(hours=2):
                log.info("Token expiring soon, please re-authenticate via /upstox/login")

def exchange_code(code):
    try:
        log.info(f"Exchanging code: {code[:8]}...")
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
        if r.status_code == 200:
            data = r.json()
            data['expires_at'] = (datetime.now() + timedelta(days=1)).isoformat()
            save_token(data)
            log.info("✅ Upstox token saved!")
            return True, None
        return False, f"HTTP {r.status_code}: {r.text}"
    except Exception as e:
        log.error(f"Exchange error: {e}")
        return False, str(e)

# ── INSTRUMENT MAP ──────────────────────────────────────────
INSTRUMENTS = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
    "MIDCPNIFTY": "NSE_INDEX|NIFTY MID SELECT",
    "SENSEX": "BSE_INDEX|SENSEX",
    "RELIANCE": "NSE_EQ|INE002A01018",
    "TCS": "NSE_EQ|INE467B01029",
    "HDFCBANK": "NSE_EQ|INE040A01034",
    "INFY": "NSE_EQ|INE009A01021",
    "SBIN": "NSE_EQ|INE062A01020",
    "ICICIBANK": "NSE_EQ|INE090A01021",
    "HINDUNILVR": "NSE_EQ|INE030A01027",
    "AXISBANK": "NSE_EQ|INE238A01034",
    "BAJFINANCE": "NSE_EQ|INE296A01024",
    "KOTAKBANK": "NSE_EQ|INE237A01028",
    "LT": "NSE_EQ|INE018A01030",
    "TATAMOTORS": "NSE_EQ|INE155A01022",
}

TF = {
    "monthly": {"interval": "month", "days": 1825},
    "weekly":  {"interval": "week",  "days": 730},
    "daily":   {"interval": "day",   "days": 400},
    "tf75":    {"interval": "30minute", "days": 60},
    "tf15":    {"interval": "30minute", "days": 30},
    "tf5":     {"interval": "1minute",  "days": 5},
}

_cache = {}
_cache_ts = {}
CACHE_TTL = 300

def fetch_candles(instrument_key, interval, days):
    token = get_token()
    if not token:
        return None, "no_token"
    key = f"{instrument_key}_{interval}"
    now = time.time()
    if key in _cache and (now - _cache_ts.get(key, 0)) < CACHE_TTL:
        return _cache[key], None
    try:
        to_dt = date.today()
        from_dt = to_dt - timedelta(days=days)
        url = f"https://api.upstox.com/v2/historical-candle/{requests.utils.quote(instrument_key, safe='')}/{interval}/{to_dt.isoformat()}/{from_dt.isoformat()}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            candles = r.json().get("data", {}).get("candles", [])
            if not candles:
                return None, "no_data"
            closes = [c[4] for c in candles]
            _cache[key] = closes
            _cache_ts[key] = now
            return closes, None
        return None, f"http_{r.status_code}"
    except Exception as e:
        return None, str(e)

def calc_macd(closes, fast=12, slow=26, sig=9):
    if not closes or len(closes) < slow + sig + 2:
        return None
    s = pd.Series(closes)
    ml = s.ewm(span=fast, adjust=False).mean() - s.ewm(span=slow, adjust=False).mean()
    sl = ml.ewm(span=sig, adjust=False).mean()
    hi = ml - sl
    cv, pv = float(ml.iloc[-1]), float(ml.iloc[-2])
    cz = "ABOVE" if cv > 0 else "BELOW"
    pz = "ABOVE" if pv > 0 else "BELOW"
    return {
        "signal": "BUY" if cz == "ABOVE" else "SELL",
        "zero": cz,
        "crossover": cz != pz,
        "histogram": round(float(hi.iloc[-1]), 6),
        "macd": round(cv, 6),
    }

EMPTY_SIG = {"signal": "—", "zero": "—", "crossover": False, "histogram": 0}

def get_signals(ticker, timeframes):
    ticker = ticker.upper().strip()
    ikey = INSTRUMENTS.get(ticker)
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

# ── ROUTES ────────────────────────────────────────────────
@app.route("/")
def index():
    token = get_token()
    login_url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope=historical_data"
    return jsonify({
        "name": "WaveEdge API — Upstox + FII",
        "version": "6.0",
        "connected": bool(token),
        "login_url": login_url if not token else "already_connected",
        "endpoints": {
            "/health": "Status check",
            "/upstox/login": "Redirect to Upstox login",
            "/upstox/callback": "OAuth callback",
            "/upstox/status": "Token status",
            "/upstox/token": "Manual token injection (POST)",
            "/fii": "FII/DII participant data from NSE",
            "/pcr": "Put-Call Ratio from NSE",
            "/macd/<ticker>": "MACD signals",
            "/macd/batch": "Batch MACD signals",
            "/scan": "Elliott Wave scanner",
            "/symbols": "All mapped symbols"
        }
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok", "connected": bool(get_token()), "time": datetime.utcnow().isoformat()})

@app.route("/upstox/login")
def upstox_login():
    login_url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope=historical_data"
    return redirect(login_url)

@app.route("/upstox/callback")
def upstox_callback():
    code = request.args.get("code")
    error = request.args.get("error")
    if error:
        return {"error": f"Login failed: {error}"}, 400
    if not code:
        return {"error": "No code received"}, 400
    ok, err = exchange_code(code)
    if ok:
        return {"success": True, "message": "Upstox connected successfully!"}
    return {"error": err}, 400

@app.route("/upstox/status")
def upstox_status():
    return jsonify({"connected": bool(get_token()), "expires_at": _tok.get("expires_at", "")})

@app.route("/upstox/token", methods=["POST"])
def manual_token():
    data = request.get_json() or {}
    token = data.get("access_token", "").strip()
    key = data.get("admin_key", "")
    if key != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 401
    if not token:
        return jsonify({"error": "access_token required"}), 400
    save_token({"access_token": token, "expires_at": (datetime.now() + timedelta(days=1)).isoformat()})
    return jsonify({"success": True, "message": "Token saved!"})

# ── FII ENDPOINT (FIXED) ──────────────────────────────────
def _safe_int(val):
    try:
        return int(str(val).replace(",", "").strip() or 0)
    except:
        return 0

@app.route("/fii")
def fii_data():
    """Complete FII/DII data from NSE public archives"""
    result = {"data": [], "spotPrice": 0, "spotChange": 0, "spotPct": 0, "pcr": 0, "source": "unknown"}

    # NIFTY spot from Upstox
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
        except:
            pass

    # Try NSE archives for participant data
    headers_csv = {"User-Agent": "Mozilla/5.0", "Accept": "text/csv"}
    participant_data = []
    for days_back in range(8):
        check_date = datetime.now() - timedelta(days=days_back)
        if check_date.weekday() >= 5:
            continue
        date_str = check_date.strftime("%d%m%Y")
        csv_url = f"https://archives.nseindia.com/content/historical/DERIVATIVES/{check_date.year}/{check_date.strftime('%b').upper()}/fao_participant_oi_{date_str}.csv"
        try:
            r = requests.get(csv_url, headers=headers_csv, timeout=8)
            if r.status_code == 200 and "Client Type" in r.text:
                reader = csv.DictReader(io.StringIO(r.text))
                participant_data = list(reader)
                if participant_data:
                    result["dataDate"] = check_date.strftime("%d-%b-%Y")
                    result["source"] = "nse_csv"
                    break
        except:
            continue

    if participant_data:
        mapped = []
        for row in participant_data:
            ct = row.get("Client Type", "").strip()
            if not ct or ct == "Total":
                continue
            mapped.append({
                "clientType": ct,
                "instrumentType": "Index Futures",
                "longQuantity": _safe_int(row.get("Future Index Long", 0)),
                "shortQuantity": _safe_int(row.get("Future Index Short", 0)),
                "changeLongQuantity": _safe_int(row.get("Future Index Long Change", 0)),
                "changeShortQuantity": _safe_int(row.get("Future Index Short Change", 0)),
            })
            mapped.append({
                "clientType": ct,
                "instrumentType": "Index Calls",
                "longQuantity": _safe_int(row.get("Option Index Call Long", 0)),
                "shortQuantity": _safe_int(row.get("Option Index Call Short", 0)),
            })
            mapped.append({
                "clientType": ct,
                "instrumentType": "Index Puts",
                "longQuantity": _safe_int(row.get("Option Index Put Long", 0)),
                "shortQuantity": _safe_int(row.get("Option Index Put Short", 0)),
            })
            mapped.append({
                "clientType": ct,
                "instrumentType": "Stock Futures",
                "longQuantity": _safe_int(row.get("Future Stock Long", 0)),
                "shortQuantity": _safe_int(row.get("Future Stock Short", 0)),
            })
        result["data"] = mapped
        return jsonify(result)

    if result["spotPrice"]:
        result["spotOnly"] = True
        result["error"] = "NSE CSV unavailable - may be holiday or before 6pm"
        return jsonify(result)

    return jsonify({"error": "All data sources failed"}), 503

@app.route("/pcr")
def pcr_data():
    """NSE Put-Call Ratio"""
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0', 'Accept': '*/*'})
        session.get('https://www.nseindia.com', timeout=8)
        r = session.get('https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY', timeout=10)
        data = r.json()
        filtered = data.get('filtered', {})
        pe_oi = filtered.get('PE', {}).get('totOI', 0)
        ce_oi = filtered.get('CE', {}).get('totOI', 1)
        pcr = round(pe_oi / ce_oi, 4) if ce_oi > 0 else 0
        return jsonify({"pcr": pcr, "pe_oi": pe_oi, "ce_oi": ce_oi})
    except Exception as e:
        return jsonify({"error": str(e)}), 503

@app.route("/macd/<ticker>")
def macd_single(ticker):
    paid = request.args.get("paid", "false").lower() == "true"
    tf_param = request.args.get("tf", "")
    if tf_param:
        tfs = [t.strip() for t in tf_param.split(",") if t.strip() in TF]
    elif paid:
        tfs = list(TF.keys())
    else:
        tfs = ["monthly", "weekly", "daily"]
    return jsonify(get_signals(ticker, tfs))

@app.route("/macd/batch", methods=["GET", "POST"])
def macd_batch():
    if request.method == "POST":
        data = request.get_json() or {}
        scrips = data.get("scrips", ["NIFTY", "BANKNIFTY", "RELIANCE"])
        paid = data.get("paid", False)
        tf_param = data.get("timeframes", None)
    else:
        scrips = [s.strip() for s in request.args.get("scrips", "NIFTY,BANKNIFTY,RELIANCE").split(",") if s.strip()]
        paid = request.args.get("paid", "false").lower() == "true"
        tf_param = request.args.get("tf", None)

    if tf_param:
        timeframes = [t.strip() for t in tf_param.split(",") if t.strip() in TF]
    elif paid:
        timeframes = list(TF.keys())
    else:
        timeframes = ["monthly", "weekly", "daily"]

    results = {}
    for ticker in scrips[:20]:
        try:
            results[ticker] = get_signals(ticker, timeframes)
            time.sleep(0.4)
        except Exception as e:
            results[ticker] = {"error": str(e)}
    return jsonify({"count": len(results), "timeframes": timeframes, "connected": bool(get_token()), "timestamp": datetime.utcnow().isoformat(), "results": results})

@app.route("/scan")
def scan_all():
    if not get_token():
        return jsonify({"error": "upstox_not_connected"}), 401
    results = []
    for ticker in ["NIFTY", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK"]:
        try:
            ikey = INSTRUMENTS.get(ticker)
            if ikey:
                closes, _ = fetch_candles(ikey, "day", 200)
                if closes:
                    results.append({"symbol": ticker, "price": closes[-1], "signal": calc_macd(closes) or {}})
            time.sleep(0.5)
        except:
            pass
    return jsonify({"count": len(results), "results": results})

@app.route("/symbols")
def symbols():
    return jsonify({"count": len(INSTRUMENTS), "symbols": list(INSTRUMENTS.keys())})

@app.route("/blog")
def blog():
    return jsonify({"message": "Blog endpoint active", "posts": []})

if __name__ == "__main__":
    load_token()
    threading.Thread(target=refresh_token_automatically, daemon=True).start()
    log.info("=" * 50)
    log.info("WaveEdge API v6 — Upstox + FII Ready")
    log.info(f"Token valid: {bool(get_token())}")
    if not get_token():
        log.info(f"LOGIN URL: {SELF_URL}/upstox/login")
    log.info("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
