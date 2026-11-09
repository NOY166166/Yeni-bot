"""BIST algoritmik trading botu.

  python main.py backtest              # tam dönem backtest + endeks karşılaştırması
  python main.py walkforward           # kayan pencere, görülmemiş veride test
  python main.py paper [--notify]      # günlük kağıt işlem (state.json)
  Ek: --demo (sahte veri) --inflation 0.45 --tickers THYAO,GARAN --positions 5
"""
import argparse
import os
from dataclasses import replace

import pandas as pd

from analytics import perf, show, trade_stats
from config import Config
from runner import run_backtest, walk_forward


def get_data(cfg, demo):
    if demo:
        from synthetic import synthetic
        return synthetic()
    from data import load_all
    return load_all(cfg)


def bench_perf(bench, idx, infl):
    if bench is None:
        return {}
    b = bench.reindex(idx, method="ffill").dropna()
    return perf(b, infl)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["backtest", "walkforward", "paper"])
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--tickers")
    ap.add_argument("--positions", type=int)
    ap.add_argument("--inflation", type=float)
    ap.add_argument("--state", default="state.json")
    ap.add_argument("--notify", action="store_true")
    a = ap.parse_args()

    cfg = Config(annual_inflation=a.inflation)
    if a.tickers:
        cfg = replace(cfg, universe=[t if "." in t else t + ".IS"
                                     for t in a.tickers.upper().split(",")])
    if a.positions:
        cfg = replace(cfg, max_positions=a.positions)
    data, bench = get_data(cfg, a.demo)
    os.makedirs("output", exist_ok=True)

    if a.cmd == "backtest":
        eng = run_backtest(cfg, data, bench)
        eq = eng.equity_series()
        show("STRATEJİ", perf(eq, cfg.annual_inflation), trade_stats(eng.trades))
        show("ENDEKS AL-TUT", bench_perf(bench, eq.index, cfg.annual_inflation))
        inv = pd.Series(eng.invested).mean()
        print(f"\nOrtalama piyasada kalma oranı: {inv:.0%}")
        eq.to_csv("output/equity.csv")
        pd.DataFrame(eng.trades).to_csv("output/trades.csv", index=False)
        print("Kaydedildi: output/equity.csv, output/trades.csv")

    elif a.cmd == "walkforward":
        folds, oos, trades = walk_forward(cfg, data, bench)
        for tr_end, te_end, best, p in folds:
            r = f"{p['toplam']:.1%}" if p else "-"
            print(f"Test {tr_end} -> {te_end} | {best} | getiri {r}")
        if oos is not None:
            show("WALK-FORWARD (sadece test dönemleri)",
                 perf(oos, cfg.annual_inflation), trade_stats(trades))
            show("ENDEKS AL-TUT (aynı dönem)", bench_perf(bench, oos.index, cfg.annual_inflation))
            oos.to_csv("output/oos_equity.csv")

    else:
        from paper import run_paper
        msg = run_paper(cfg, data, bench, a.state)
        print(msg)
        if a.notify:
            from notify import telegram
            telegram(msg)


if __name__ == "__main__":
    main()
