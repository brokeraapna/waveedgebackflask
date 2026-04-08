def sma(data, period):
    if len(data) < period:
        return None
    return sum(data[-period:]) / period

def ema(data, period):
    k = 2 / (period + 1)
    ema_val = sum(data[:period]) / period
    for price in data[period:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val
