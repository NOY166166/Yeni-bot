import json
import os

import pandas as pd

from engine import Engine
from strategy import get_features, make_regime


def run_paper(cfg, data, bench, state_path="state.json"):
    rows, dates = get_features(data, cfg)
    eng = Engine(cfg, rows, make_regime(bench, cfg))
    if os.path.exists(state_path):
        with open(state_path) as fh:
            st = json.load(fh)
        eng.load_state(st)
        last = pd.Timestamp(st["last_date"])
        new = [d for d in dates if d > last]
    else:
        new = [dates[-1]]  # ilk çalıştırma: sadece son bardan başla
    n_before = len(eng.trades)
    for d in new:
        eng.process_day(d)
    if not new:
        return f"Yeni veri yok (son işlenen gün: {st['last_date']})."
    with open(state_path, "w") as fh:
        json.dump(eng.to_state(new[-1]), fh, indent=2, default=float)
    return report(eng, new[-1], eng.trades[n_before:])


def report(eng, d, new_trades):
    lines = [f"BIST bot | {d.date()} | Özsermaye {eng.equity_now():,.0f} TL "
             f"(nakit {eng.cash:,.0f})"]
    if new_trades:
        lines.append("Kapanan işlemler:")
        for t in new_trades:
            lines.append(f"  {t['ticker']} {t['ret']:+.1%} ({t['reason']})")
    if eng.pos:
        lines.append("Açık pozisyonlar:")
        for t, p in eng.pos.items():
            last = eng.last_close.get(t, p["entry"])
            lines.append(f"  {t} {p['shares']} adet | giriş {p['entry']:.2f} | "
                         f"son {last:.2f} ({last / p['entry'] - 1:+.1%}) | stop {p['stop']:.2f}")
    else:
        lines.append("Açık pozisyon yok.")
    pend = eng.pending
    if pend["sell"] or pend["buy"]:
        lines.append("YARIN AÇILIŞTA (kağıt emir):")
        for t in pend["sell"]:
            lines.append(f"  SAT {t}")
        for o in pend["buy"]:
            lines.append(f"  AL  {o['ticker']} (ATR {o['atr']:.2f})")
    else:
        lines.append("Yarın için emir yok.")
    return "\n".join(lines)
