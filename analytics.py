import numpy as np
import pandas as pd


def perf(eq, infl=None):
    eq = eq.dropna()
    r = eq.pct_change().dropna()
    if len(r) < 20:
        return {}
    years = len(r) / 252
    ratio = eq.iloc[-1] / eq.iloc[0]
    cagr = ratio ** (1 / years) - 1
    dd = (eq / eq.cummax() - 1).min()
    sd = r.std()
    neg = r[r < 0].std()
    out = {"toplam": ratio - 1, "yillik": cagr, "maks_dusus": dd,
           "volatilite": sd * np.sqrt(252),
           "sharpe": np.sqrt(252) * r.mean() / sd if sd > 0 else 0.0,
           "sortino": np.sqrt(252) * r.mean() / neg if neg and neg > 0 else 0.0,
           "calmar": cagr / abs(dd) if dd < 0 else 0.0}
    if infl is not None:
        out["reel_yillik"] = (1 + cagr) / (1 + infl) - 1
    return out


def trade_stats(trades):
    if not trades:
        return {}
    pnl = [t["pnl"] for t in trades]
    wins = sum(x for x in pnl if x > 0)
    losses = -sum(x for x in pnl if x <= 0)
    holds = [(pd.Timestamp(t["exit_date"]) - pd.Timestamp(t["entry_date"])).days
             for t in trades]
    return {"islem": len(trades),
            "kazanma_orani": sum(1 for x in pnl if x > 0) / len(pnl),
            "profit_factor": wins / losses if losses > 0 else float("inf"),
            "ort_islem_getirisi": float(np.mean([t["ret"] for t in trades])),
            "ort_tutma_gun": float(np.mean(holds))}


def show(title, p, ts=None):
    print(f"\n=== {title} ===")
    if not p:
        print("  (yeterli veri yok)")
        return
    f = lambda k: f"{p[k]:.1%}"
    print(f"  Toplam {f('toplam')} | Yıllık {f('yillik')} | Maks düşüş {f('maks_dusus')}")
    print(f"  Sharpe {p['sharpe']:.2f} | Sortino {p['sortino']:.2f} | "
          f"Calmar {p['calmar']:.2f} | Vol {f('volatilite')}")
    if "reel_yillik" in p:
        print(f"  Reel yıllık (enflasyona göre): {f('reel_yillik')}")
    if ts:
        print(f"  İşlem {ts['islem']} | Kazanma {ts['kazanma_orani']:.0%} | "
              f"PF {ts['profit_factor']:.2f} | Ort. işlem {ts['ort_islem_getirisi']:.1%} | "
              f"Ort. tutma {ts['ort_tutma_gun']:.0f} gün")
