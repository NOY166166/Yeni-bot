"""Saatlik BIST tarayıcı: momentum + hacim patlaması, bilanço ve haber filtresi.
Gerçek emir göndermez; Telegram'a AL/STOP/HEDEF fiyatları yollar. Yatırım tavsiyesi değildir.

  python scanner.py          # canlı (GitHub Actions saatlik çalıştırır)
  python scanner.py --demo   # sahte veriyle deneme
"""
import json
import math
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from indicators import atr, ema, rsi, sma

TZ = "Europe/Istanbul"


def env(name, default):
    return os.getenv(name) or default


CAPITAL = float(env("CAPITAL", "100000"))
RISK = float(env("RISK_PCT", "0.01"))        # işlem başına sermayenin %1'i
MAX_DAY = int(env("MAX_PER_DAY", "5"))       # günde en fazla öneri
MAX_RUN = int(env("MAX_PER_RUN", "2"))       # tarama başına en fazla öneri
STRICT = env("STRICT_FUND", "1") == "1"      # bilanço doğrulanamazsa ele
COMM = float(env("COMMISSION", "0.002"))     # işlem başı komisyon (kurumunla teyit et)
MIN_TURNOVER = 30_000_000                    # 20 günlük ort. günlük TL hacim
STATE = env("SCAN_STATE", "scan_state.json")

NEG = ["zarar", "soruşturma", "iflas", "konkordato", "spk", "ceza", "dava", "işlem yasağı",
       "tedbir", "temerrüt", "gözaltı", "haciz", "manipülasyon", "operasyon", "tasfiye",
       "kâr uyarısı", "kar uyarısı", "borç yapılandırma", "bağımsız denetim", "olumsuz görüş"]


def tr_lower(s):
    return s.replace("İ", "i").replace("I", "ı").lower()


# ---------- BIST fiyat adımı ----------
def tick(p):
    for lim, t in ((20, 0.01), (50, 0.02), (100, 0.05), (250, 0.10),
                   (500, 0.25), (1000, 0.50), (2500, 1.0)):
        if p < lim:
            return t
    return 2.5


def rnd(p, mode="near"):
    t = tick(p)
    n = p / t
    n = math.floor(n + 1e-9) if mode == "down" else (math.ceil(n - 1e-9) if mode == "up" else round(n))
    return round(n * t, 2)


# ---------- veri ----------
def load_universe(path="universe.txt"):
    out = []
    for line in open(path, encoding="utf-8"):
        s = line.split("#")[0].strip().upper()
        if s:
            out.append(s if "." in s else s + ".IS")
    return out


def load_hourly(tickers, chunk=80):
    import yfinance as yf
    out = {}
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        try:
            raw = yf.download(part, period="120d", interval="60m", auto_adjust=True,
                              group_by="ticker", progress=False, threads=True)
        except Exception as e:
            print("İndirme hatası:", e)
            continue
        for t in part:
            try:
                df = raw[t].rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
                df = df.dropna().copy()
                idx = df.index
                df.index = idx.tz_localize(TZ) if idx.tz is None else idx.tz_convert(TZ)
                df = df[~df.index.duplicated()]
                if len(df) > 300:
                    out[t] = df
            except Exception:
                pass
    print(f"{len(out)}/{len(tickers)} hisse için veri alındı")
    return out


def fundamentals(t):
    """Yahoo verisi BIST için eksik olabilir. None = doğrulanamadı."""
    try:
        import yfinance as yf
        info = yf.Ticker(t).get_info()
    except Exception:
        return None
    eps, pm = info.get("trailingEps"), info.get("profitMargins")
    cr, de, roe = info.get("currentRatio"), info.get("debtToEquity"), info.get("returnOnEquity")
    if eps is None and pm is None:
        return None
    ok = ((eps is None or eps > 0) and (pm is None or pm > 0)
          and (cr is None or cr >= 1.0) and (de is None or de <= 200))
    parts = []
    if eps is not None:
        parts.append(f"EPS {eps:.2f}")
    if pm is not None:
        parts.append(f"marj {pm:.0%}")
    if cr is not None:
        parts.append(f"cari oran {cr:.1f}")
    if roe is not None:
        parts.append(f"ROE {roe:.0%}")
    return {"ok": ok, "txt": ", ".join(parts)}


def bad_news(t):
    """Google Haber başlıklarında olumsuz kelime ara (KAP değildir!). None = kontrol edilemedi."""
    q = urllib.parse.quote(f"{t.replace('.IS', '')} hisse when:3d")
    url = f"https://news.google.com/rss/search?q={q}&hl=tr&gl=TR&ceid=TR:tr"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            root = ET.fromstring(r.read())
    except Exception:
        return None
    titles = [(i.findtext("title") or "") for i in root.iter("item")][:15]
    return [x for x in titles if any(k in tr_lower(x) for k in NEG)]


# ---------- tarama ----------
def evaluate(t, h, now):
    h = h[h.index + pd.Timedelta(minutes=60) <= now]      # sadece tamamlanmış saatlik barlar
    if len(h) < 300 or h.index[-1].date() != now.date():
        return None
    day = h.index[-1].date()
    today = h[h.index.date == day]
    if len(today) < 2 or today["volume"].iloc[-1] <= 0:
        return None
    last, hr = h.iloc[-1], h.index[-1].hour

    # hacim patlaması: son bar ve gün içi birikimli, aynı saatlerin ortalamasına göre
    same = h[(h.index.hour == hr) & (h.index.date < day)]["volume"].tail(20)
    if len(same) < 10 or same.mean() <= 0:
        return None
    rvol = last["volume"] / same.mean()
    cum = h[h.index.hour <= hr]["volume"].groupby(h[h.index.hour <= hr].index.date).sum()
    prior = cum[cum.index != day].tail(20)
    if day not in cum.index or prior.mean() <= 0:
        return None
    rvol_day = cum[day] / prior.mean()

    # günlük trend / likidite
    d = h.groupby(h.index.date).agg(close=("close", "last"), volume=("volume", "sum"))
    if len(d) < 60:
        return None
    if d["close"].iloc[-1] <= sma(d["close"], 50).iloc[-1] or d["close"].iloc[-1] / d["close"].iloc[-21] - 1 <= 0:
        return None
    if (d["close"] * d["volume"]).iloc[-21:-1].mean() < MIN_TURNOVER:
        return None

    # saatlik momentum
    c = h["close"]
    mom = c.iloc[-1] / c.iloc[-7] - 1
    chg_day = c.iloc[-1] / d["close"].iloc[-2] - 1
    tp = (today["high"] + today["low"] + today["close"]) / 3
    vwap = (tp * today["volume"]).sum() / today["volume"].sum()
    e20, e50 = ema(c, 20).iloc[-1], ema(c, 50).iloc[-1]
    r = rsi(c).iloc[-1]
    if not (rvol >= 2.0 and rvol_day >= 1.5 and 0.01 <= mom <= 0.06 and 0.005 <= chg_day <= 0.07
            and last["close"] > vwap and last["close"] > e20 > e50 and r < 80):
        return None

    # fiyat seviyeleri
    a = atr(h).iloc[-1]
    if math.isnan(a):
        return None
    entry = last["close"]
    dist = max(1.5 * a, 0.006 * entry)
    if dist > 0.04 * entry:
        return None
    gross = 2 * dist / entry
    if gross < 0.012:                      # komisyon sonrası anlamlı değil
        return None
    score = 0.5 * min(rvol, 6) / 6 + 0.5 * min(mom / 0.05, 1)
    return {"t": t, "score": score, "rvol": rvol, "mom": mom, "entry": rnd(entry),
            "entry_max": rnd(entry * 1.003, "up"), "stop": rnd(entry - dist, "down"),
            "target": rnd(entry + 2 * dist, "down"), "bar_end": h.index[-1] + pd.Timedelta(minutes=60)}


# ---------- durum ----------
def load_state(today):
    try:
        st = json.load(open(STATE))
        if st.get("date") == today:
            return st
    except Exception:
        pass
    return {"date": today, "sent": [], "open": {}}


def demo_data():
    rng = np.random.default_rng(3)
    days = pd.bdate_range(end=pd.Timestamp("2026-11-10"), periods=130)
    idx = pd.DatetimeIndex([d + pd.Timedelta(hours=hh) for d in days for hh in range(10, 18)]
                           ).tz_localize(TZ)
    data = {}
    for i in range(30):
        strong = i < 2
        r = rng.normal(0.0001 + (0.0003 if strong else 0), 0.004, len(idx))
        vol = rng.lognormal(13.6, 0.3, len(idx))
        if strong:
            r[-8:] = 0.0025
            vol[-8:] *= 2.5
            vol[-1] *= 1.6
        close = 100 * np.exp(np.cumsum(r))
        op = np.r_[close[0], close[:-1]]
        hi = np.maximum(op, close) * (1 + np.abs(rng.normal(0, 0.002, len(idx))))
        lo = np.minimum(op, close) * (1 - np.abs(rng.normal(0, 0.002, len(idx))))
        data[f"DEMO{i:02d}.IS"] = pd.DataFrame(
            {"open": op, "high": hi, "low": lo, "close": close, "volume": vol}, index=idx)
    return data, idx[-1] + pd.Timedelta(minutes=61)


def main():
    demo = "--demo" in sys.argv
    if demo:
        data, now = demo_data()
    else:
        now = pd.Timestamp.now(tz=TZ)
        if now.weekday() >= 5 or not (10 <= now.hour < 18):
            print("Piyasa kapalı, çıkılıyor.")
            return
        data = load_hourly(load_universe())
        if not data or max(h.index[-1].date() for h in data.values()) != now.date():
            print("Bugüne ait veri yok (tatil ya da veri gecikmesi).")
            return
    st = load_state(str(now.date()))
    msgs = []

    # 1) açık önerilerin stop/hedef takibi
    for t, o in list(st["open"].items()):
        h = data.get(t)
        seg = h[h.index >= pd.Timestamp(o["since"])] if h is not None else None
        if seg is None or seg.empty:
            continue
        if seg["low"].min() <= o["stop"]:
            msgs.append(f"STOP {t}: {o['stop']} görüldü. Pozisyonu açtıysan SAT.")
            del st["open"][t]
        elif seg["high"].max() >= o["target"]:
            msgs.append(f"HEDEF {t}: {o['target']} görüldü. Kâr al.")
            del st["open"][t]
    if st["open"] and now.hour >= 17 and not demo:
        msgs.append("Gün sonu: açık gün içi pozisyonları kapanıştan önce kapat: "
                    + ", ".join(st["open"]))

    # 2) yeni fırsatlar
    slots = min(MAX_RUN, MAX_DAY - len(st["sent"]))
    if slots > 0 and (demo or 10 <= now.hour <= 15):
        cands = [c for c in (evaluate(t, h, now) for t, h in data.items()) if c]
        cands.sort(key=lambda c: -c["score"])
        picked = []
        for c in cands[:15]:
            if len(picked) >= slots:
                break
            if c["t"] in st["sent"]:
                continue
            if demo:
                f, n = {"ok": True, "txt": "demo"}, []
            else:
                f, n = fundamentals(c["t"]), bad_news(c["t"])
            if f is None and STRICT:
                continue
            if f is not None and not f["ok"]:
                continue
            if n:
                continue
            c["f"], c["n"] = f, n
            picked.append(c)
        for c in picked:
            dist = c["entry"] - c["stop"]
            shares = int(min(CAPITAL * RISK / dist, 0.25 * CAPITAL / c["entry"]))
            net = (c["target"] / c["entry"] - 1) - 2 * COMM
            code = c["t"].replace(".IS", "")
            msgs.append(
                f"{code}: AL limit {c['entry']} (en fazla {c['entry_max']})\n"
                f"  STOP {c['stop']} | HEDEF {c['target']} (net ~{net:.1%})\n"
                f"  Hacim x{c['rvol']:.1f} | 6s momentum {c['mom']:+.1%} | VWAP üstü\n"
                f"  Bilanço: {c['f']['txt'] if c['f'] else 'doğrulanamadı'}"
                f" | Haber: {'temiz' if c['n'] is not None else 'kontrol edilemedi'}\n"
                f"  Adet ~{shares} (sermaye {CAPITAL:,.0f}, risk %{RISK*100:g})")
            st["sent"].append(c["t"])
            st["open"][c["t"]] = {"entry": c["entry"], "stop": c["stop"], "target": c["target"],
                                  "since": c["bar_end"].isoformat()}
        if picked:
            msgs.append("KAP'ı kontrol et, stop emrini girmeyi unutma. Veri ~15 dk gecikmeli olabilir.")

    json.dump(st, open(STATE, "w"), indent=1)
    if not msgs:
        print("Uygun fırsat yok.")
        return
    text = f"BIST tarama {now:%H:%M}\n" + "\n".join(msgs)
    print(text)
    if not demo:
        from notify import telegram
        telegram(text)


if __name__ == "__main__":
    main()
