"""İnternetsiz deneme için sahte veri (rejimli, gürültülü)."""
import numpy as np
import pandas as pd


def synthetic(n=24, days=2800, seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2014-01-01", periods=days)
    drift = 0.0007 * np.sin(np.arange(days) / 250) + 0.0004
    market = drift + rng.normal(0, 0.011, days)
    data, closes = {}, []
    for i in range(n):
        beta = rng.uniform(0.6, 1.4)
        r = beta * market + rng.normal(0.0002, 0.015, days)
        for k in range(1, days):
            r[k] += 0.05 * r[k - 1]  # hafif momentum
        close = 100 * np.exp(np.cumsum(r))
        op = np.r_[close[0], close[:-1]] * (1 + rng.normal(0, 0.004, days))
        hi = np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.006, days)))
        lo = np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.006, days)))
        vol = rng.integers(1_000_000, 5_000_000, days)
        data[f"DEMO{i:02d}.IS"] = pd.DataFrame(
            {"open": op, "high": hi, "low": lo, "close": close, "volume": vol}, index=idx)
        closes.append(close)
    bench = pd.Series(np.mean(closes, axis=0), index=idx)
    return data, bench
