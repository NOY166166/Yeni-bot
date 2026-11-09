"""Özellik/sinyal üretimi. Tüm göstergeler nedensel (geleceği görmez)."""
import pandas as pd

from indicators import adx, atr, ema, macd, rsi, sma

_CACHE = {}


def build_features(df, cfg):
    c, h, v = df["close"], df["high"], df["volume"]
    ema_f, ema_s, trend = ema(c, cfg.fast), ema(c, cfg.slow), sma(c, cfg.trend)
    _, _, hist = macd(c)
    r = rsi(c, cfg.rsi_len)
    roc = c.pct_change(cfg.rank_len)

    conds = [
        c > trend,                                   # uzun vadeli yükseliş
        ema_f > ema_s,                               # orta vadeli trend
        (hist > 0) & (hist > hist.shift(1)),         # momentum ivmeleniyor
        adx(df) > cfg.adx_min,                       # trend gücü yeterli
        (r > 50) & (r < cfg.rsi_buy_max),            # aşırı alımda değil
        roc > 0,                                     # göreli güç pozitif
    ]
    out = pd.DataFrame(index=df.index)
    out["open"], out["high"], out["low"], out["close"] = df["open"], h, df["low"], c
    out["score"] = sum(x.astype(int) for x in conds)
    hh = h.rolling(cfg.breakout_len).max().shift(1)
    turnover = (c * v).rolling(20).mean()
    out["breakout"] = (c > hh) & (turnover >= cfg.min_turnover)
    out["exit_trend"] = c < ema_s
    out["rank"] = roc
    out["atr"] = atr(df)
    out["trend"] = trend
    return out.dropna(subset=["atr", "rank", "trend"])


def get_features(data, cfg):
    """(rows, dates) döner; parametre kombinasyonu başına önbelleğe alır."""
    key = (id(data), cfg.fast, cfg.slow, cfg.trend, cfg.rsi_len, cfg.rsi_buy_max,
           cfg.adx_min, cfg.breakout_len, cfg.rank_len, cfg.min_turnover)
    if key not in _CACHE:
        feats = {t: build_features(df, cfg) for t, df in data.items()}
        feats = {t: f for t, f in feats.items() if len(f) > 50}
        rows = {t: f.to_dict("index") for t, f in feats.items()}
        dates = sorted(set().union(*[set(f.index) for f in feats.values()]))
        _CACHE[key] = (rows, dates)
    return _CACHE[key]


def make_regime(bench, cfg):
    if bench is None or not cfg.regime_filter:
        return {}
    ok = bench > sma(bench, cfg.regime_len)
    return {d: bool(x) for d, x in ok.items()}
