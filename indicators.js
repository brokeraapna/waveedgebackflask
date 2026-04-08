// ============================================================
// WaveEdge — Technical Indicators Engine
// Supports: EMA, SMA, RSI, MACD, Bollinger Bands, Breakout
// Input: Array of candles [timestamp, open, high, low, close, volume]
// ============================================================

/**
 * Extract close prices from candle array
 * Candles from Upstox: [timestamp, open, high, low, close, volume]
 */
function getCloses(candles) { return candles.map(c => c[4]); }
function getHighs(candles)  { return candles.map(c => c[2]); }
function getLows(candles)   { return candles.map(c => c[3]); }
function getVolumes(candles){ return candles.map(c => c[5]); }

// ─── EMA ─────────────────────────────────────────────────────
function ema(data, period) {
  if (data.length < period) return null;
  const k = 2 / (period + 1);
  let emaVal = data.slice(0, period).reduce((a, b) => a + b, 0) / period;
  for (let i = period; i < data.length; i++) {
    emaVal = data[i] * k + emaVal * (1 - k);
  }
  return emaVal;
}

// ─── SMA ─────────────────────────────────────────────────────
function sma(data, period) {
  if (data.length < period) return null;
  const slice = data.slice(-period);
  return slice.reduce((a, b) => a + b, 0) / period;
}

// ─── EMA Array (all values, not just last) ───────────────────
function emaArray(data, period) {
  if (data.length < period) return [];
  const k = 2 / (period + 1);
  const result = [];
  let emaVal = data.slice(0, period).reduce((a, b) => a + b, 0) / period;
  result.push(emaVal);
  for (let i = period; i < data.length; i++) {
    emaVal = data[i] * k + emaVal * (1 - k);
    result.push(emaVal);
  }
  return result;
}

// ─── RSI (Wilder's Method) ───────────────────────────────────
function rsi(data, period = 14) {
  if (data.length < period + 1) return null;

  let gains = 0, losses = 0;
  for (let i = 1; i <= period; i++) {
    const diff = data[i] - data[i - 1];
    if (diff > 0) gains += diff;
    else losses += Math.abs(diff);
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;

  for (let i = period + 1; i < data.length; i++) {
    const diff = data[i] - data[i - 1];
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? Math.abs(diff) : 0;
    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
  }

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return parseFloat((100 - 100 / (1 + rs)).toFixed(2));
}

// ─── MACD ─────────────────────────────────────────────────────
function macd(data, fastPeriod = 12, slowPeriod = 26, signalPeriod = 9) {
  if (data.length < slowPeriod + signalPeriod) return null;

  const fastEMA = emaArray(data, fastPeriod);
  const slowEMA = emaArray(data, slowPeriod);

  // Align arrays (slow has fewer elements)
  const offset = fastEMA.length - slowEMA.length;
  const macdLine = slowEMA.map((val, i) => fastEMA[i + offset] - val);

  const signalLine = emaArray(macdLine, signalPeriod);
  const lastMacd   = macdLine[macdLine.length - 1];
  const lastSignal = signalLine[signalLine.length - 1];
  const histogram  = lastMacd - lastSignal;

  // Detect crossover
  const prevHistogram = macdLine[macdLine.length - 2] -
    (signalLine.length >= 2 ? signalLine[signalLine.length - 2] : lastSignal);

  let crossover = 'NEUTRAL';
  if (prevHistogram < 0 && histogram > 0) crossover = 'BULLISH_CROSS'; // BUY
  if (prevHistogram > 0 && histogram < 0) crossover = 'BEARISH_CROSS'; // SELL

  return {
    macd:      parseFloat(lastMacd.toFixed(4)),
    signal:    parseFloat(lastSignal.toFixed(4)),
    histogram: parseFloat(histogram.toFixed(4)),
    crossover,
  };
}

// ─── Bollinger Bands ─────────────────────────────────────────
function bollingerBands(data, period = 20, stdDevMult = 2) {
  if (data.length < period) return null;
  const slice = data.slice(-period);
  const mid   = slice.reduce((a, b) => a + b, 0) / period;
  const variance = slice.reduce((sum, val) => sum + Math.pow(val - mid, 2), 0) / period;
  const stdDev = Math.sqrt(variance);
  const upper  = mid + stdDevMult * stdDev;
  const lower  = mid - stdDevMult * stdDev;
  const ltp    = data[data.length - 1];
  const pos    = ((ltp - lower) / (upper - lower)) * 100; // 0-100%

  let bbSignal = 'NEUTRAL';
  if (ltp >= upper)  bbSignal = 'OVERBOUGHT';
  if (ltp <= lower)  bbSignal = 'OVERSOLD';

  return {
    upper:  parseFloat(upper.toFixed(2)),
    middle: parseFloat(mid.toFixed(2)),
    lower:  parseFloat(lower.toFixed(2)),
    position: parseFloat(pos.toFixed(1)),
    signal: bbSignal,
  };
}

// ─── Breakout Detection ───────────────────────────────────────
function breakout(highs, lows, closes, volumes, lookback = 52) {
  // lookback in trading days (52 weeks ≈ 252 days, but use 52 for weekly breakout)
  if (closes.length < lookback + 1) return null;

  const recentHighs   = highs.slice(-(lookback + 1), -1);  // exclude today
  const recentLows    = lows.slice(-(lookback + 1), -1);
  const recentVolumes = volumes.slice(-20);

  const highestHigh = Math.max(...recentHighs);
  const lowestLow   = Math.min(...recentLows);
  const avgVolume   = recentVolumes.reduce((a, b) => a + b, 0) / recentVolumes.length;
  const todayClose  = closes[closes.length - 1];
  const todayVol    = volumes[volumes.length - 1];
  const volRatio    = todayVol / avgVolume;

  let signal = 'NEUTRAL';
  let strength = 0;

  if (todayClose > highestHigh) {
    signal = 'BREAKOUT_BUY';
    strength = Math.min(100, Math.round(((todayClose - highestHigh) / highestHigh) * 1000));
    if (volRatio > 1.5) strength += 20; // Volume confirmation
  } else if (todayClose < lowestLow) {
    signal = 'BREAKDOWN_SELL';
    strength = Math.min(100, Math.round(((lowestLow - todayClose) / lowestLow) * 1000));
    if (volRatio > 1.5) strength += 20;
  }

  return {
    signal,
    strength: Math.min(100, strength),
    highestHigh: parseFloat(highestHigh.toFixed(2)),
    lowestLow: parseFloat(lowestLow.toFixed(2)),
    volumeRatio: parseFloat(volRatio.toFixed(2)),
  };
}

// ─── Composite Signal Generator ───────────────────────────────
// Returns: { signal: 'BUY'|'SELL'|'NEUTRAL', confidence: 0-100, reasons: [] }
function generateSignal(candles) {
  if (!candles || candles.length < 50) return { signal: 'NEUTRAL', confidence: 0, reasons: ['Insufficient data'] };

  const closes  = getCloses(candles);
  const highs   = getHighs(candles);
  const lows    = getLows(candles);
  const volumes = getVolumes(candles);

  const rsiVal  = rsi(closes, 14);
  const macdVal = macd(closes);
  const bbVal   = bollingerBands(closes);
  const boVal   = breakout(highs, lows, closes, volumes, 52);

  let score   = 0;
  const reasons = [];

  // RSI scoring
  if (rsiVal !== null) {
    if (rsiVal < 35)       { score += 25; reasons.push(`RSI Oversold (${rsiVal})`); }
    else if (rsiVal < 50)  { score += 10; reasons.push(`RSI Neutral-Bullish (${rsiVal})`); }
    else if (rsiVal > 70)  { score -= 25; reasons.push(`RSI Overbought (${rsiVal})`); }
    else if (rsiVal > 55)  { score -= 10; reasons.push(`RSI Neutral-Bearish (${rsiVal})`); }
  }

  // MACD scoring
  if (macdVal) {
    if (macdVal.crossover === 'BULLISH_CROSS') { score += 35; reasons.push('MACD Bullish Crossover ✅'); }
    if (macdVal.crossover === 'BEARISH_CROSS') { score -= 35; reasons.push('MACD Bearish Crossover ❌'); }
    if (macdVal.histogram > 0 && macdVal.macd > 0) { score += 10; reasons.push('MACD Above Zero'); }
    if (macdVal.histogram < 0 && macdVal.macd < 0) { score -= 10; reasons.push('MACD Below Zero'); }
  }

  // Bollinger Bands scoring
  if (bbVal) {
    if (bbVal.signal === 'OVERSOLD')    { score += 20; reasons.push('BB Lower Band Touch'); }
    if (bbVal.signal === 'OVERBOUGHT')  { score -= 20; reasons.push('BB Upper Band Touch'); }
  }

  // Breakout scoring
  if (boVal) {
    if (boVal.signal === 'BREAKOUT_BUY')    { score += 40; reasons.push(`52W Breakout 🚀 (Vol: ${boVal.volumeRatio}x)`); }
    if (boVal.signal === 'BREAKDOWN_SELL')  { score -= 40; reasons.push(`52W Breakdown 📉 (Vol: ${boVal.volumeRatio}x)`); }
  }

  let signal = 'NEUTRAL';
  if (score >= 30)  signal = 'BUY';
  if (score <= -30) signal = 'SELL';
  const confidence = Math.min(100, Math.abs(score));

  return {
    signal,
    confidence,
    score,
    reasons,
    indicators: { rsi: rsiVal, macd: macdVal, bb: bbVal, breakout: boVal },
  };
}

module.exports = { ema, sma, emaArray, rsi, macd, bollingerBands, breakout, generateSignal, getCloses, getHighs, getLows, getVolumes };
