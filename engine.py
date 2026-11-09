"""Günlük portföy motoru. Backtest ve kağıt işlem AYNI kodu kullanır.

Akış: gün sonu kapanışta sinyal -> ertesi gün AÇILIŞTA emir -> gün içi stop kontrolü.
"""
import math


class Engine:
    def __init__(self, cfg, rows, regime=None):
        self.cfg, self.rows, self.regime = cfg, rows, regime or {}
        self.cash = float(cfg.initial_cash)
        self.pos = {}
        self.pending = {"sell": [], "buy": []}
        self.cool = {}
        self.day_i = 0
        self.last_close = {}
        self.trades = []
        self.equity = {}
        self.invested = {}

    # ---------- yardımcılar ----------
    def equity_now(self):
        return self.cash + sum(p["shares"] * self.last_close.get(t, p["entry"])
                               for t, p in self.pos.items())

    def _buy(self, t, r, atr, d, eq):
        c = self.cfg
        price = r["open"] * (1 + c.slippage)
        stop_dist = c.atr_stop_mult * atr
        if stop_dist <= 0 or math.isnan(stop_dist):
            return
        shares = int(min(c.risk_per_trade * eq / stop_dist,
                         c.max_position_pct * eq / price,
                         self.cash / (price * (1 + c.commission))))
        if shares < 1:
            return
        cost = shares * price * (1 + c.commission)
        self.cash -= cost
        self.pos[t] = {"shares": shares, "entry": price, "cost": cost,
                       "stop": price - stop_dist, "high": price,
                       "date": d.strftime("%Y-%m-%d")}

    def _sell(self, t, px, d, reason):
        c = self.cfg
        p = self.pos.pop(t)
        price = px * (1 - c.slippage)
        proceeds = p["shares"] * price * (1 - c.commission)
        self.cash += proceeds
        pnl = proceeds - p["cost"]
        self.trades.append({"ticker": t, "entry_date": p["date"],
                            "exit_date": d.strftime("%Y-%m-%d"),
                            "entry": round(p["entry"], 4), "exit": round(price, 4),
                            "shares": p["shares"], "pnl": round(pnl, 2),
                            "ret": pnl / p["cost"], "reason": reason})
        if reason == "stop":
            self.cool[t] = self.day_i

    # ---------- ana adım ----------
    def process_day(self, d):
        c = self.cfg
        self.day_i += 1

        # 1) dünkü emirleri bugünün açılışında doldur (önce satış)
        for t in self.pending["sell"]:
            r = self.rows[t].get(d)
            if r is not None and t in self.pos:
                self._sell(t, r["open"], d, "trend")
        eq = self.equity_now()
        for o in self.pending["buy"]:
            t = o["ticker"]
            r = self.rows[t].get(d)
            if r is None or t in self.pos or len(self.pos) >= c.max_positions:
                continue
            self._buy(t, r, o["atr"], d, eq)
        self.pending = {"sell": [], "buy": []}

        # 2) gün içi stop (açılış stop'un altındaysa açılıştan çıkılır)
        for t in list(self.pos):
            r = self.rows[t].get(d)
            if r is not None and r["low"] <= self.pos[t]["stop"]:
                self._sell(t, min(r["open"], self.pos[t]["stop"]), d, "stop")

        # 3) gün sonu: takip eden stop güncelle
        for t, p in self.pos.items():
            r = self.rows[t].get(d)
            if r is None:
                continue
            self.last_close[t] = r["close"]
            p["high"] = max(p["high"], r["close"])
            p["stop"] = max(p["stop"], p["high"] - c.trail_mult * r["atr"])

        # 4) yarın için sinyaller
        sells = []
        for t in self.pos:
            r = self.rows[t].get(d)
            if r is not None and r["exit_trend"]:
                sells.append(t)
        regime_ok = (not c.regime_filter) or self.regime.get(d, True)
        slots = c.max_positions - (len(self.pos) - len(sells))
        buys = []
        if regime_ok and slots > 0:
            cands = []
            for t, rw in self.rows.items():
                if t in self.pos:
                    continue
                r = rw.get(d)
                if r is None:
                    continue
                if self.day_i - self.cool.get(t, -10**9) < c.cooldown_days:
                    continue
                if r["score"] >= c.min_score and r["breakout"]:
                    cands.append((r["rank"], t, r["atr"]))
            cands.sort(reverse=True)
            buys = [{"ticker": t, "atr": float(a), "rank": float(k)}
                    for k, t, a in cands[:slots]]
        self.pending = {"sell": sells, "buy": buys}

        # 5) kayıt
        eq = self.equity_now()
        self.equity[d] = eq
        self.invested[d] = 1 - self.cash / eq if eq > 0 else 0

    def equity_series(self):
        import pandas as pd
        return pd.Series(self.equity, dtype=float)

    # ---------- kalıcılık (kağıt işlem) ----------
    def to_state(self, last_date):
        return {"cash": self.cash, "pos": self.pos, "pending": self.pending,
                "cool": self.cool, "day_i": self.day_i,
                "last_date": last_date.strftime("%Y-%m-%d"),
                "last_close": self.last_close, "trades": self.trades}

    def load_state(self, st):
        self.cash, self.pos, self.pending = st["cash"], st["pos"], st["pending"]
        self.cool, self.day_i = st["cool"], st["day_i"]
        self.last_close, self.trades = st["last_close"], st["trades"]
