import os
import requests
import eventlet
eventlet.monkey_patch()

from flask import Flask, request, redirect, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ==============================
# ENV VARIABLES
# ==============================
UPSTOX_API_KEY = os.getenv("UPSTOX_API_KEY")
UPSTOX_CLIENT_SECRET = os.getenv("UPSTOX_CLIENT_SECRET")
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI")

ACCESS_TOKEN = None

# ==============================
# HOME ROUTE
# ==============================
@app.route("/")
def home():
    return jsonify({
        "status": "live",
        "token_valid": ACCESS_TOKEN is not None,
        "login_url": "/upstox/login",
        "endpoints": [
            "/upstox/login",
            "/upstox/callback",
            "/health"
        ]
    })

# ==============================
# HEALTH CHECK
# ==============================
@app.route("/health")
def health():
    return {"status": "ok"}

# ==============================
# LOGIN ROUTE
# ==============================
@app.route("/upstox/login")
def upstox_login():
    login_url = (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code"
        f"&client_id={UPSTOX_API_KEY}"
        f"&redirect_uri={UPSTOX_REDIRECT_URI}"
    )
    return redirect(login_url)

# ==============================
# CALLBACK ROUTE (MOST IMPORTANT)
# ==============================
@app.route("/upstox/callback")
def upstox_callback():
    global ACCESS_TOKEN

    code = request.args.get("code")

    if not code:
        return "❌ No code received"

    url = "https://api.upstox.com/v2/login/authorization/token"

    payload = {
        "code": code,
        "client_id": UPSTOX_API_KEY,
        "client_secret": UPSTOX_CLIENT_SECRET,
        "redirect_uri": UPSTOX_REDIRECT_URI,
        "grant_type": "authorization_code"
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    response = requests.post(url, data=payload, headers=headers)

    try:
        data = response.json()
    except:
        return f"❌ Invalid response: {response.text}"

    if "access_token" in data:
        ACCESS_TOKEN = data["access_token"]
        return jsonify({
            "message": "✅ Login successful",
            "access_token": ACCESS_TOKEN
        })
    else:
        return jsonify({
            "error": "❌ Token exchange failed",
            "response": data
        })

# ==============================
# RUN APP (RENDER COMPATIBLE)
# ==============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
