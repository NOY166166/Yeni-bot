import datetime as dt
import hashlib
import os
import pickle

import pandas as pd


def _clean(df):
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    df = df[~df.index.duplicated()].dropna(subset=["open", "high", "low", "close"])
    return df[df["close"] > 0].sort_index()


def load_all(cfg, cache_dir=".cache"):
    """(data: {ticker: df}, bench: Series) döner. Günlük önbellek kullanır."""
    os.makedirs(cache_dir, exist_ok=True)
    tickers = list(cfg.universe) + [cfg.benchmark]
    h = hashlib.md5((",".join(tickers) + cfg.start).encode()).hexdigest()[:8]
    fn = os.path.join(cache_dir, f"prices_{dt.date.today()}_{h}.pkl")
    if os.path.exists(fn):
        with open(fn, "rb") as fh:
            return pickle.load(fh)

    import yfinance as yf
    raw = yf.download(tickers, start=cfg.start, auto_adjust=True,
                      group_by="ticker", progress=False, threads=True)
    data = {}
    for t in cfg.universe:
        try:
            df = _clean(raw[t].copy())
            if len(df) > 300:
                data[t] = df
            else:
                print(f"Uyarı: {t} yetersiz veri, atlandı")
        except Exception as e:
            print(f"Uyarı: {t} alınamadı ({e})")
    try:
        bench = _clean(raw[cfg.benchmark].copy())["close"]
    except Exception:
        bench = None
        print("Uyarı: endeks verisi yok, rejim filtresi devre dışı")
    if not data:
        raise SystemExit("Hiç veri alınamadı. İnternet/yfinance'i kontrol et.")
    with open(fn, "wb") as fh:
        pickle.dump((data, bench), fh)
    return data, bench
