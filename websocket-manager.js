// ============================================================
// WaveEdge — WebSocket Manager (Upstox Live Feed → Socket.IO)
// Strategy: REST polling (reliable) + Protobuf WS (optional upgrade)
// ============================================================
const axios = require('axios');
const WebSocket = require('ws');
const fs = require('fs');
const path = require('path');
const { NIFTY50, getAllInstrumentKeys } = require('./instruments');

const TOKEN_FILE = path.join(__dirname, 'token.json');

function getAccessToken() {
  if (!fs.existsSync(TOKEN_FILE)) return null;
  const token = JSON.parse(fs.readFileSync(TOKEN_FILE));
  return token.access_token;
}

// ─── Cache for live prices ───────────────────────────────────
let liveCache = {};       // { "NSE_EQ|...": { ltp, change, changePct, ... } }
let wsConnection = null;
let pollingInterval = null;

// ─── REST Polling (Primary Method) ───────────────────────────
// Polls Upstox LTP API every 2 seconds and broadcasts via Socket.IO
async function startPolling(io) {
  if (pollingInterval) clearInterval(pollingInterval);
  console.log('▶️  Starting LTP polling for Nifty 50...');

  const refreshFeed = async () => {
    const token = getAccessToken();
    if (!token) return;

    try {
      // Upstox allows up to 500 instruments per call
      const allKeys = getAllInstrumentKeys();
      const res = await axios.get('https://api.upstox.com/v2/market-quote/ltp', {
        params: { instrument_key: allKeys },
        headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
      });

      const feeds = res.data?.data || {};
      const update = {};

      for (const [key, val] of Object.entries(feeds)) {
        const instrument = NIFTY50.find(i => i.key === key);
        update[key] = {
          key,
          symbol: instrument?.symbol || key,
          name:   instrument?.name || key,
          sector: instrument?.sector || '',
          ltp:    val.last_price,
          cp:     val.last_price, // close price placeholder (REST LTP doesn't return cp directly)
        };
      }

      // Get full market data for change %
      const fullRes = await axios.get('https://api.upstox.com/v2/market-quote/quotes', {
        params: { instrument_key: allKeys },
        headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
      });

      const fullFeeds = fullRes.data?.data || {};
      for (const [key, val] of Object.entries(fullFeeds)) {
        if (update[key]) {
          const prevClose = val.ohlc?.close || val.last_price;
          const change    = val.last_price - prevClose;
          const changePct = prevClose ? ((change / prevClose) * 100).toFixed(2) : 0;
          update[key] = {
            ...update[key],
            ltp:       val.last_price,
            open:      val.ohlc?.open,
            high:      val.ohlc?.high,
            low:       val.ohlc?.low,
            prevClose,
            change:    parseFloat(change.toFixed(2)),
            changePct: parseFloat(changePct),
            volume:    val.volume,
          };
        }
      }

      liveCache = { ...liveCache, ...update };
      io.emit('ltp_update', update); // Broadcast to all connected clients
    } catch (err) {
      // Silently ignore during market hours polling errors
    }
  };

  await refreshFeed(); // Immediate first call
  pollingInterval = setInterval(refreshFeed, 3000); // Every 3 seconds
}

function stopPolling() {
  if (pollingInterval) {
    clearInterval(pollingInterval);
    pollingInterval = null;
    console.log('⏹️  LTP polling stopped.');
  }
}

// ─── Upstox WebSocket Feed (Protobuf, Advanced) ──────────────
// NOTE: This requires the Upstox proto file to decode binary messages.
// Download proto from: https://github.com/upstox/upstox-nodejs/blob/master/lib/proto/MarketDataFeed.proto
// and install: npm install protobufjs
async function startWebSocketFeed(io, instrumentKeys = []) {
  const token = getAccessToken();
  if (!token) { console.log('❌ No token for WebSocket'); return; }

  try {
    // Step 1: Get authorized WS URL
    const authRes = await axios.get('https://api.upstox.com/v2/feed/market-data-feed/authorize', {
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
    });
    const wsUrl = authRes.data?.data?.authorizedRedirectUri;
    if (!wsUrl) throw new Error('No WS URL returned');

    console.log('🔌 Connecting to Upstox WebSocket...');
    wsConnection = new WebSocket(wsUrl, { headers: { Authorization: `Bearer ${token}` } });

    wsConnection.on('open', () => {
      console.log('✅ Upstox WebSocket connected');
      // Subscribe to instruments
      const subscribeMsg = {
        guid: 'waveedge-' + Date.now(),
        method: 'sub',
        data: {
          mode: 'full',
          instrumentKeys: instrumentKeys.length > 0 ? instrumentKeys : NIFTY50.slice(0, 10).map(i => i.key),
        },
      };
      wsConnection.send(Buffer.from(JSON.stringify(subscribeMsg)));
    });

    wsConnection.on('message', (data) => {
      // Data is binary Protobuf — decode using protobufjs
      // For now, log raw length and emit raw binary to backend buffer
      // Full Protobuf decode requires the .proto schema — see README
      try {
        // Attempt JSON parse first (some responses are JSON)
        const msg = JSON.parse(data.toString());
        io.emit('ws_raw', msg);
      } catch {
        // Binary Protobuf data — skip until proto decoder is set up
        io.emit('ws_tick', { raw: true, size: data.length, ts: Date.now() });
      }
    });

    wsConnection.on('close', () => {
      console.log('🔴 Upstox WebSocket closed. Reconnecting in 5s...');
      setTimeout(() => startWebSocketFeed(io, instrumentKeys), 5000);
    });

    wsConnection.on('error', (err) => {
      console.error('WS Error:', err.message);
    });
  } catch (err) {
    console.error('WS setup failed:', err.message);
  }
}

function stopWebSocket() {
  if (wsConnection) { wsConnection.close(); wsConnection = null; }
}

function getLiveCache() { return liveCache; }

module.exports = { startPolling, stopPolling, startWebSocketFeed, stopWebSocket, getLiveCache };
