"""
WaveEdge Backend v4 - Upstox API + Auto Token Management
"""
from flask import Flask, jsonify, request, redirect
from flask_cors import CORS
import pandas as pd
import numpy as np
from datetime import datetime, date
import threading, time, logging, json, os, re
import requests

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("waveedge")
app = Flask(__name__)
CORS(app)

# ─── CONFIG ───────────────────────────────────────────────
UPSTOX_CLIENT_ID     = os.environ.get("UPSTOX_CLIENT_ID",     "0993c447-0d76-44dc-9fd2-aef1c19a9695")
UPSTOX_CLIENT_SECRET = os.environ.get("UPSTOX_CLIENT_SECRET", "")  # set in Render env vars
UPSTOX_REDIRECT_URI  = os.environ.get("UPSTOX_REDIRECT_URI",  "https://waveedge-backend-1.onrender.com/upstox/callback")
ADMIN_KEY            = os.environ.get("ADMIN_KEY",             "waveedge2024")
SELF_URL             = os.environ.get("SELF_URL",              "https://waveedge-backend-1.onrender.com")
TOKEN_FILE           = "upstox_token.json"
POSTS_FILE           = "blog_posts.json"

# ─── TOKEN MANAGEMENT ─────────────────────────────────────
_token_data = {}

def load_token():
    global _token_data
    try:
        with open(TOKEN_FILE, 'r') as f:
            _token_data = json.load(f)
            log.info(f"Token loaded, expires: {_token_data.get('expires_at','?')}")
    except:
        _token_data = {}

def save_token(data):
    global _token_data
    _token_data = data
    try:
        with open(TOKEN_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        log.error(f"Save token error: {e}")

def get_access_token():
    """Return valid access token or None."""
    if not _token_data.get('access_token'):
        return None
    # Upstox tokens expire daily - check date
    expires_at = _token_data.get('expires_at', '')
    if expires_at and expires_at < date.today().isoformat():
        log.warning("Token expired")
        return None
    return _token_data['access_token']

def exchange_code_for_token(code):
    """Exchange auth code for access token."""
    try:
        resp = requests.post(
            "https://api.upstox.com/v2/login/authorization/token",
            data={
                "code":          code,
                "client_id":     UPSTOX_CLIENT_ID,
                "client_secret": UPSTOX_CLIENT_SECRET,
                "redirect_uri":  UPSTOX_REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            data['expires_at'] = date.today().isoformat()
            save_token(data)
            log.info("Token exchanged successfully!")
            return True
        else:
            log.error(f"Token exchange failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        log.error(f"Token exchange error: {e}")
        return False

# ─── UPSTOX INSTRUMENT KEYS ───────────────────────────────
# Format: NSE_EQ|ISIN or NSE_INDEX|Nifty 50
INSTRUMENT_MAP = {
    "NIFTY":       "NSE_INDEX|Nifty 50",
    "NIFTY50":     "NSE_INDEX|Nifty 50",
    "BANKNIFTY":   "NSE_INDEX|Nifty Bank",
    "SENSEX":      "BSE_INDEX|SENSEX",
    "RELIANCE":    "NSE_EQ|INE002A01018",
    "TCS":         "NSE_EQ|INE467B01029",
    "HDFCBANK":    "NSE_EQ|INE040A01034",
    "INFY":        "NSE_EQ|INE009A01021",
    "SBIN":        "NSE_EQ|INE062A01020",
    "TATAMOTORS":  "NSE_EQ|INE155A01022",
    "WIPRO":       "NSE_EQ|INE075A01022",
    "ICICIBANK":   "NSE_EQ|INE090A01021",
    "AXISBANK":    "NSE_EQ|INE238A01034",
    "BAJFINANCE":  "NSE_EQ|INE296A01024",
    "ADANIENT":    "NSE_EQ|INE423A01024",
    "MARUTI":      "NSE_EQ|INE585B01010",
    "SUNPHARMA":   "NSE_EQ|INE044A01036",
    "KOTAKBANK":   "NSE_EQ|INE237A01028",
    "LT":          "NSE_EQ|INE018A01030",
    "HINDUNILVR":  "NSE_EQ|INE030A01027",
    "ASIANPAINT":  "NSE_EQ|INE021A01026",
    "ITC":         "NSE_EQ|INE154A01025",
    "ONGC":        "NSE_EQ|INE213A01029",
    "NTPC":        "NSE_EQ|INE733E01010",
    "POWERGRID":   "NSE_EQ|INE752E01010",
}

TF_MAP = {
    # Upstox intervals
    "monthly": {"interval": "1month", "days": 1825},  # 5 years
    "weekly":  {"interval": "1week",  "days": 730},   # 2 years
    "daily":   {"interval": "day",    "days": 365},   # 1 year
    "tf75":    {"interval": "30minute","days": 60},   # 60 days (closest to 75m)
    "tf15":    {"interval": "15minute","days": 60},
    "tf5":     {"interval": "5minute", "days": 30},
}

# Cache
_cache = {}; _cache_ts = {}; CACHE_TTL = 300

DEFAULT_SCRIPS = [
    "NIFTY","BANKNIFTY","RELIANCE","TCS","HDFCBANK",
    "INFY","SBIN","TATAMOTORS","ICICIBANK","AXISBANK"
]

# ─── UPSTOX DATA FETCH ────────────────────────────────────
def fetch_upstox_candles(instrument_key, interval, days):
    """Fetch OHLCV from Upstox historical API."""
    token = get_access_token()
    if not token:
        return None

    cache_key = f"{instrument_key}_{interval}"
    now = time.time()
    if cache_key in _cache and (now - _cache_ts.get(cache_key, 0)) < CACHE_TTL:
        return _cache[cache_key]

    try:
        to_date   = date.today().isoformat()
        from_date = date.fromordinal(date.today().toordinal() - days).isoformat()

        # Upstox v2 historical candles endpoint
        url = f"https://api.upstox.com/v2/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            candles = data.get("data", {}).get("candles", [])
            if not candles:
                return None
            # Candle format: [timestamp, open, high, low, close, volume, oi]
            closes = [c[4] for c in candles]
            _cache[cache_key] = closes
            _cache_ts[cache_key] = now
            return closes
        else:
            log.warning(f"Upstox {instrument_key} {interval}: {resp.status_code} {resp.text[:100]}")
            return None
    except Exception as e:
        log.warning(f"Upstox fetch error {instrument_key}: {e}")
        return None

# ─── MACD CALCULATION ─────────────────────────────────────
def calc_macd(closes, fast=12, slow=26, sig=9):
    if not closes or len(closes) < slow + sig + 2:
        return None
    s = pd.Series(closes)
    ml = s.ewm(span=fast, adjust=False).mean() - s.ewm(span=slow, adjust=False).mean()
    sl = ml.ewm(span=sig,  adjust=False).mean()
    hist = ml - sl
    cv, pv = float(ml.iloc[-1]), float(ml.iloc[-2])
    cz = "ABOVE" if cv > 0 else "BELOW"
    pz = "ABOVE" if pv > 0 else "BELOW"
    return {
        "signal":    "BUY" if cz == "ABOVE" else "SELL",
        "zero":      cz,
        "crossover": cz != pz,
        "histogram": round(float(hist.iloc[-1]), 6),
        "macd":      round(cv, 6),
    }

def get_signals(ticker, timeframes):
    ticker = ticker.upper().strip()
    instrument_key = INSTRUMENT_MAP.get(ticker)
    result = {"symbol": ticker, "instrument_key": instrument_key or "unknown", "timeframes": {}}
    empty = {"signal": "—", "zero": "—", "crossover": False, "histogram": 0}

    if not instrument_key:
        for tf in timeframes:
            result["timeframes"][tf] = {**empty, "error": "symbol not mapped"}
        result["timestamp"] = datetime.utcnow().isoformat()
        return result

    for tf in timeframes:
        if tf not in TF_MAP:
            result["timeframes"][tf] = empty
            continue
        cfg = TF_MAP[tf]
        closes = fetch_upstox_candles(instrument_key, cfg["interval"], cfg["days"])
        if not closes or len(closes) < 35:
            result["timeframes"][tf] = {**empty, "error": "insufficient data"}
            continue
        sig = calc_macd(closes)
        result["timeframes"][tf] = sig if sig else empty

    result["timestamp"] = datetime.utcnow().isoformat()
    return result

# ─── BLOG / POSTS ─────────────────────────────────────────
def load_posts():
    try:
        with open(POSTS_FILE, 'r') as f: return json.load(f)
    except: return []

def save_posts_file(posts):
    try:
        with open(POSTS_FILE, 'w') as f: json.dump(posts[:100], f, indent=2)
    except: pass

# ─── BACKGROUND THREADS ───────────────────────────────────
def bg_cache_warmer():
    time.sleep(20)
    while True:
        token = get_access_token()
        if token:
            log.info("Warming Upstox cache...")
            for t in DEFAULT_SCRIPS:
                try: get_signals(t, ["monthly", "weekly", "daily"]); time.sleep(1)
                except: pass
            log.info("Cache warm done.")
        else:
            log.warning("No valid token — skipping cache warm")
        time.sleep(600)

def bg_keep_alive():
    time.sleep(60)
    while True:
        try: requests.get(SELF_URL + "/health", timeout=10)
        except: pass
        time.sleep(600)

# ─── ROUTES ───────────────────────────────────────────────
@app.route("/")
def index():
    token = get_access_token()
    login_url = (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code&client_id={UPSTOX_CLIENT_ID}"
        f"&redirect_uri={UPSTOX_REDIRECT_URI}&scope=historical_data"
    )
    return jsonify({
        "name":       "WaveEdge API v4 (Upstox)",
        "status":     "live",
        "token_valid": bool(token),
        "login_url":  login_url if not token else None,
        "endpoints":  ["/upstox/login", "/upstox/callback", "/macd/<ticker>", "/macd/batch", "/health"]
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok", "token_valid": bool(get_access_token()), "time": datetime.utcnow().isoformat()})

@app.route("/upstox/login")
def upstox_login():
    """Redirect to Upstox login page."""
    login_url = (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code&client_id={UPSTOX_CLIENT_ID}"
        f"&redirect_uri={UPSTOX_REDIRECT_URI}&scope=historical_data"
    )
    return redirect(login_url)

@app.route("/upstox/callback")
def upstox_callback():
    """Handle OAuth callback from Upstox."""
    code  = request.args.get("code")
    error = request.args.get("error")
    if error:
        return f"<h2>Login Error: {error}</h2><p><a href='/upstox/login'>Try Again</a></p>", 400
    if not code:
        return "<h2>No code received</h2><p><a href='/upstox/login'>Try Again</a></p>", 400
    success = exchange_code_for_token(code)
    if success:
        return """
        <html><head><style>
        body{font-family:Arial,sans-serif;background:#020c14;color:#00e5ff;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;}
        .box{background:#061525;border:1px solid #00e5ff;border-radius:14px;padding:40px;text-align:center;max-width:400px;}
        h2{color:#00ff88;font-size:28px;margin-bottom:10px;}
        p{color:#4d8099;font-size:14px;margin-bottom:20px;}
        a{display:inline-block;background:linear-gradient(135deg,#00e5ff,#00ff88);color:#000;padding:12px 28px;border-radius:7px;text-decoration:none;font-weight:700;}
        </style></head><body>
        <div class="box">
          <h2>&#10004; Connected!</h2>
          <p>Upstox API is now connected to WaveEdge.<br>Real-time NSE data is live.</p>
          <a href="https://waveedge.in">Go to WaveEdge &#8594;</a>
        </div></body></html>
        """
    else:
        return f"""
        <html><head><style>body{{font-family:Arial;background:#020c14;color:#ff1744;display:flex;align-items:center;justify-content:center;min-height:100vh;}}.box{{background:#061525;border:1px solid #ff1744;border-radius:14px;padding:40px;text-align:center;}}</style></head><body>
        <div class="box"><h2>&#10060; Token Exchange Failed</h2><p style="color:#4d8099">Check that UPSTOX_CLIENT_SECRET is set in Render Environment Variables.</p>
        <a href="/upstox/login" style="background:#ff1744;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;">Try Again</a></div></body></html>
        """, 400

@app.route("/upstox/status")
def upstox_status():
    token = get_access_token()
    login_url = (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code&client_id={UPSTOX_CLIENT_ID}"
        f"&redirect_uri={UPSTOX_REDIRECT_URI}&scope=historical_data"
    )
    return jsonify({
        "connected":  bool(token),
        "expires_at": _token_data.get("expires_at", ""),
        "login_url":  login_url
    })

@app.route("/macd/<ticker>")
def macd_single(ticker):
    paid = request.args.get("paid", "false").lower() == "true"
    tf_p = request.args.get("tf", "")
    if tf_p:   tfs = [t.strip() for t in tf_p.split(",") if t.strip() in TF_MAP]
    elif paid: tfs = list(TF_MAP.keys())
    else:      tfs = ["monthly", "weekly", "daily"]
    return jsonify(get_signals(ticker, tfs))

@app.route("/macd/batch", methods=["POST", "GET"])
def macd_batch():
    if request.method == "POST":
        data   = request.get_json() or {}
        scrips = data.get("scrips", DEFAULT_SCRIPS)
        paid   = data.get("paid", False)
        tfs    = data.get("timeframes", None)
    else:
        scrips = [s.strip() for s in request.args.get("scrips", ",".join(DEFAULT_SCRIPS)).split(",") if s.strip()]
        paid   = request.args.get("paid", "false").lower() == "true"
        tfs    = request.args.get("tf", None)

    scrips = scrips[:20]
    if tfs:    timeframes = [t.strip() for t in tfs.split(",") if t.strip() in TF_MAP]
    elif paid: timeframes = list(TF_MAP.keys())
    else:      timeframes = ["monthly", "weekly", "daily"]

    results = {}
    for ticker in scrips:
        try:   results[ticker] = get_signals(ticker, timeframes); time.sleep(0.5)
        except Exception as e: results[ticker] = {"error": str(e), "symbol": ticker}

    return jsonify({
        "count":      len(results),
        "timeframes": timeframes,
        "timestamp":  datetime.utcnow().isoformat(),
        "results":    results
    })

@app.route("/blog")
def blog():
    posts = load_posts()
    cat   = request.args.get("cat", "all")
    if cat != "all": posts = [p for p in posts if p.get("cat") == cat]
    return jsonify({"count": len(posts), "posts": posts[:50]})

@app.route("/symbols")
def symbols():
    return jsonify({"symbols": list(INSTRUMENT_MAP.keys()), "count": len(INSTRUMENT_MAP)})

# ─── STARTUP ──────────────────────────────────────────────
if __name__ == "__main__":
    load_token()
    threading.Thread(target=bg_cache_warmer, daemon=True).start()
    threading.Thread(target=bg_keep_alive,   daemon=True).start()
    log.info("WaveEdge API v4 (Upstox) starting...")
    app.run(host="0.0.0.0", port=5000, debug=False)
