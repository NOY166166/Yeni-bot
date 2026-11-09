import itertools
from dataclasses import replace

import pandas as pd

from analytics import perf
from engine import Engine
from strategy import get_features, make_regime

GRID = dict(fast=[10, 20], slow=[50, 100], atr_stop_mult=[2.0, 3.0], min_score=[4, 5])


def run_backtest(cfg, data, bench, start=None, end=None):
    rows, dates = get_features(data, cfg)
    eng = Engine(cfg, rows, make_regime(bench, cfg))
    for d in dates:
        if start is not None and d < start:
            continue
        if end is not None and d >= end:
            break
        eng.process_day(d)
    return eng


def walk_forward(cfg, data, bench, train_years=4, test_years=1):
    """Eğitim penceresinde parametre seç, görülmemiş test penceresinde ölç."""
    _, dates = get_features(data, cfg)
    first, last = dates[0], dates[-1]
    keys = list(GRID)
    combos = [dict(zip(keys, v)) for v in itertools.product(*GRID.values())]
    t0, folds, rets, trades = first, [], [], []
    while True:
        tr_end = t0 + pd.DateOffset(years=train_years)
        te_end = tr_end + pd.DateOffset(years=test_years)
        if tr_end >= last:
            break
        best, best_s = combos[0], -1e9
        for kw in combos:
            eng = run_backtest(replace(cfg, **kw), data, bench, t0, tr_end)
            s = perf(eng.equity_series()).get("sharpe", -9)
            if len(eng.trades) < 5:
                s = -9
            if s > best_s:
                best, best_s = kw, s
        eng = run_backtest(replace(cfg, **best), data, bench, tr_end, te_end)
        eq = eng.equity_series()
        if len(eq) > 2:
            rets.append(eq.pct_change().dropna())
            trades += eng.trades
            folds.append((tr_end.date(), min(te_end, last).date(), best, perf(eq)))
        t0 = t0 + pd.DateOffset(years=test_years)
    if not rets:
        return folds, None, trades
    oos = (1 + pd.concat(rets)).cumprod() * cfg.initial_cash
    return folds, oos, trades
