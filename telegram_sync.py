"""
WaveEdge Telegram Auto-Sync
Watches @ewagaurav Telegram channel and auto-posts to the blog API.

How it works:
1. Polls Telegram channel RSS feed every 5 minutes
2. Detects new posts
3. Parses symbol, bias, target, SL from post text
4. Saves to a JSON file that the main site can read via /blog endpoint

Add this to your app.py or run as separate process on Render.
"""

import requests
import json
import os
import re
import time
import logging
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS

log = logging.getLogger("tg-sync")

# ─────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────
TELEGRAM_CHANNEL = "ewagaurav"          # your channel username
POSTS_FILE = "blog_posts.json"          # where posts are saved
MAX_POSTS = 100                          # keep last 100 posts
POLL_INTERVAL = 300                      # check every 5 minutes
ADMIN_KEY = os.environ.get("ADMIN_KEY", "waveedge2024")  # set in Render env vars

# ─────────────────────────────────────────────────────────
# TELEGRAM RSS FEED PARSER
# ─────────────────────────────────────────────────────────
def fetch_telegram_posts():
    """Fetch latest posts from Telegram channel via RSS."""
    try:
        url = f"https://rsshub.app/telegram/channel/{TELEGRAM_CHANNEL}"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            # Try alternative
            url2 = f"https://tg.i-c-a.su/rss/{TELEGRAM_CHANNEL}"
            resp = requests.get(url2, timeout=15)
        if resp.status_code != 200:
            log.warning(f"RSS fetch failed: {resp.status_code}")
            return []

        # Parse RSS XML
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)
        channel = root.find('channel')
        if not channel:
            return []

        items = []
        for item in channel.findall('item')[:20]:
            title_el = item.find('title')
            desc_el  = item.find('description')
            link_el  = item.find('link')
            date_el  = item.find('pubDate')

            title = title_el.text if title_el is not None else ""
            desc  = desc_el.text  if desc_el  is not None else ""
            link  = link_el.text  if link_el  is not None else ""
            date  = date_el.text  if date_el  is not None else ""

            # Clean HTML tags from description
            clean = re.sub(r'<[^>]+>', '', desc).strip()

            items.append({
                "title": title.strip() or clean[:60],
                "body":  clean,
                "link":  link,
                "date":  date,
                "source": "telegram"
            })
        return items
    except Exception as e:
        log.error(f"Telegram RSS error: {e}")
        return []

# ─────────────────────────────────────────────────────────
# POST PARSER — extract symbol, bias, target, SL
# ─────────────────────────────────────────────────────────
def parse_post(text):
    """Auto-detect trading info from post text."""
    text_upper = text.upper()

    # Symbol detection
    sym = ""
    for s in ["NIFTY50","BANKNIFTY","NIFTY","RELIANCE","TCS","HDFCBANK","INFY",
              "SBIN","TATAMOTORS","BTCUSDT","ETHUSDT","GOLD","EURUSD","AAPL","NVDA"]:
        if s in text_upper:
            sym = f"NSE:{s}" if s not in ["BTCUSDT","ETHUSDT","GOLD","EURUSD","AAPL","NVDA"] else s
            break

    # Category
    cat = "nse"
    if any(x in text_upper for x in ["BTC","ETH","CRYPTO","BITCOIN","ETHEREUM"]):
        cat = "crypto"
    elif any(x in text_upper for x in ["EUR","GBP","USD","FOREX","DOLLAR"]):
        cat = "forex"
    elif any(x in text_upper for x in ["AAPL","NVDA","TSLA","NASDAQ","NYSE"]):
        cat = "us"
    elif "EDUCATION" in text_upper or "LEARN" in text_upper:
        cat = "education"

    # Bias
    bias = "neutral"
    bull_score = len(re.findall(r'\b(BULLISH|BUY|LONG|UPSIDE|POSITIVE|BREAKOUT|UP)\b', text_upper))
    bear_score = len(re.findall(r'\b(BEARISH|SELL|SHORT|DOWNSIDE|NEGATIVE|BREAKDOWN|DOWN)\b', text_upper))
    if bull_score > bear_score: bias = "bullish"
    elif bear_score > bull_score: bias = "bearish"

    # Wave position
    wave = "Wave Analysis"
    wave_match = re.search(r'WAVE\s*[①②③④⑤ABCDE1-5]+', text_upper)
    if wave_match:
        wave = wave_match.group(0).title()

    # Target
    tgt = ""
    tgt_match = re.search(r'(?:TARGET|TGT|TP)[:\s]+([₹$]?[\d,\.]+)', text, re.IGNORECASE)
    if tgt_match: tgt = tgt_match.group(1)

    # Stop Loss
    sl = ""
    sl_match = re.search(r'(?:STOP.?LOSS|SL|STOPLOSS)[:\s]+([₹$]?[\d,\.]+)', text, re.IGNORECASE)
    if sl_match: sl = sl_match.group(1)

    return {"symbol": sym, "cat": cat, "bias": bias, "wave": wave, "target": tgt, "sl": sl}

# ─────────────────────────────────────────────────────────
# BLOG POSTS STORAGE
# ─────────────────────────────────────────────────────────
def load_posts():
    try:
        with open(POSTS_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_posts(posts):
    with open(POSTS_FILE, 'w') as f:
        json.dump(posts[:MAX_POSTS], f, indent=2)

def post_exists(posts, link):
    return any(p.get("tg_link") == link for p in posts)

# ─────────────────────────────────────────────────────────
# SYNC LOOP
# ─────────────────────────────────────────────────────────
def sync_telegram():
    """Fetch new Telegram posts and save to blog."""
    log.info("Syncing Telegram posts...")
    tg_posts = fetch_telegram_posts()
    if not tg_posts:
        log.info("No posts fetched")
        return 0

    existing = load_posts()
    new_count = 0

    for tp in reversed(tg_posts):  # oldest first
        if post_exists(existing, tp["link"]):
            continue
        parsed = parse_post(tp["body"])
        new_post = {
            "id":       int(time.time() * 1000) + new_count,
            "title":    tp["title"] or tp["body"][:60],
            "symbol":   parsed["symbol"],
            "cat":      parsed["cat"],
            "wave":     parsed["wave"],
            "bias":     parsed["bias"],
            "target":   parsed["target"],
            "sl":       parsed["sl"],
            "body":     tp["body"],
            "chart":    "https://www.tradingview.com/chart/",
            "date":     datetime.utcnow().isoformat(),
            "featured": len(existing) == 0 and new_count == 0,
            "source":   "telegram",
            "tg_link":  tp["link"]
        }
        existing.insert(0, new_post)
        new_count += 1
        log.info(f"  New post: {new_post['title'][:50]}")

    if new_count > 0:
        save_posts(existing)
        log.info(f"Synced {new_count} new posts")
    return new_count

def bg_sync_loop():
    """Background thread: sync every 5 minutes."""
    time.sleep(10)  # wait for server to start
    while True:
        try:
            sync_telegram()
        except Exception as e:
            log.error(f"Sync error: {e}")
        time.sleep(POLL_INTERVAL)

# ─────────────────────────────────────────────────────────
# FLASK ROUTES (add to main app.py)
# ─────────────────────────────────────────────────────────
"""
Add these routes to your main app.py:

@app.route("/blog")
def blog_posts():
    posts = load_posts()
    cat = request.args.get("cat", "all")
    if cat != "all":
        posts = [p for p in posts if p.get("cat") == cat]
    limit = int(request.args.get("limit", 20))
    return jsonify({"count": len(posts), "posts": posts[:limit]})

@app.route("/blog/sync", methods=["POST"])
def manual_sync():
    key = request.headers.get("X-Admin-Key", "")
    if key != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 401
    count = sync_telegram()
    return jsonify({"synced": count})

@app.route("/blog/post", methods=["POST"])
def manual_post():
    # Let site admin manually add a post
    key = request.headers.get("X-Admin-Key", "")
    if key != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json() or {}
    posts = load_posts()
    data["id"] = int(time.time() * 1000)
    data["date"] = datetime.utcnow().isoformat()
    data["source"] = "manual"
    posts.insert(0, data)
    save_posts(posts)
    return jsonify({"success": True, "id": data["id"]})
"""

# ─────────────────────────────────────────────────────────
# HOW TO ENABLE IN YOUR RENDER BACKEND
# ─────────────────────────────────────────────────────────
"""
STEP 1: Copy the routes above into your app.py

STEP 2: Add this import at top of app.py:
  from telegram_sync import sync_telegram, load_posts, bg_sync_loop, save_posts

STEP 3: Add this after app startup in app.py:
  threading.Thread(target=bg_sync_loop, daemon=True).start()

STEP 4: Add ADMIN_KEY env var in Render:
  Go to Render → waveedge-backend-1 → Environment → Add:
  Key: ADMIN_KEY   Value: (your secret key)

STEP 5: Push to GitHub → Render redeploys automatically

STEP 6: Update signals in waveedge.in to fetch from:
  GET https://waveedge-backend-1.onrender.com/blog
  → returns all your Telegram posts as JSON

That's it! Every post on @ewagaurav auto-appears on waveedge.in within 5 minutes.
"""

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing Telegram sync...")
    count = sync_telegram()
    print(f"Synced {count} posts")
    posts = load_posts()
    print(f"Total posts: {len(posts)}")
    if posts:
        print(f"Latest: {posts[0]['title']}")
