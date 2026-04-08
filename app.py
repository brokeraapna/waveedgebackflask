from flask import Flask, redirect, request, jsonify
from flask_socketio import SocketIO
import requests, json, os, time
from websocket_manager import start_polling

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

API_KEY = os.getenv("UPSTOX_API_KEY")
API_SECRET = os.getenv("UPSTOX_API_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

TOKEN_FILE = "token.json"

# ================= TOKEN =================
def save_token(data):
    data["created_at"] = int(time.time() * 1000)
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)

def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    return json.load(open(TOKEN_FILE))

# ================= AUTH =================
@app.route("/login")
def login():
    url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={API_KEY}&redirect_uri={REDIRECT_URI}"
    return redirect(url)

@app.route("/callback")
def callback():
    code = request.args.get("code")

    res = requests.post(
        "https://api.upstox.com/v2/login/authorization/token",
        json={
            "code": code,
            "client_id": API_KEY,
            "client_secret": API_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code"
        }
    )

    data = res.json()
    save_token(data)
    return "✅ Connected!"

# ================= TOKEN REFRESH =================
def get_valid_token():
    token = load_token()
    now = int(time.time() * 1000)

    if now - token["created_at"] > token["expires_in"] * 1000 - 60000:
        res = requests.post(
            "https://api.upstox.com/v2/login/refresh/token",
            json={"refresh_token": token["refresh_token"]}
        )
        token = res.json()
        save_token(token)

    return token["access_token"]

# ================= PROFILE =================
@app.route("/profile")
def profile():
    token = get_valid_token()

    res = requests.get(
        "https://api.upstox.com/v2/user/profile",
        headers={"Authorization": f"Bearer {token}"}
    )

    return jsonify(res.json())

# ================= START =================
@app.route("/")
def home():
    return "🚀 WaveEdge Flask Running"

if __name__ == "__main__":
    start_polling(socketio, get_valid_token)
    socketio.run(app, host="0.0.0.0", port=5000)
