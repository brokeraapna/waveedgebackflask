import requests, time
from instruments import NIFTY50

live_cache = {}

def start_polling(socketio, get_token_func):
    def run():
        while True:
            try:
                token = get_token_func()
                keys = [i["key"] for i in NIFTY50]

                res = requests.get(
                    "https://api.upstox.com/v2/market-quote/quotes",
                    params={"instrument_key": keys},
                    headers={"Authorization": f"Bearer {token}"}
                )

                data = res.json().get("data", {})
                update = {}

                for key, val in data.items():
                    update[key] = {
                        "ltp": val["last_price"],
                        "open": val["ohlc"]["open"],
                        "high": val["ohlc"]["high"],
                        "low": val["ohlc"]["low"],
                        "volume": val["volume"]
                    }

                socketio.emit("ltp_update", update)
                time.sleep(3)

            except Exception as e:
                print("Polling error:", e)
                time.sleep(5)

    socketio.start_background_task(run)
