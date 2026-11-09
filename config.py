from dataclasses import dataclass, field
from typing import Optional

# Endeks bileşenleri zamanla değişir; kendi listenle değiştirebilirsin.
BIST30 = ["AKBNK", "ARCLK", "ASELS", "ASTOR", "BIMAS", "BRSAN", "EKGYO", "ENKAI",
          "EREGL", "FROTO", "GARAN", "GUBRF", "HEKTS", "ISCTR", "KCHOL", "KONTR",
          "KRDMD", "ODAS", "OYAKC", "PGSUS", "SAHOL", "SASA", "SISE", "TCELL",
          "THYAO", "TOASO", "TUPRS", "YKBNK", "TTKOM", "TAVHL"]


@dataclass
class Config:
    universe: list = field(default_factory=lambda: [f"{t}.IS" for t in BIST30])
    benchmark: str = "XU100.IS"
    start: str = "2015-01-01"
    # --- portföy / maliyet ---
    initial_cash: float = 100_000.0
    commission: float = 0.002        # işlem başı komisyon+BSMV varsayımı
    slippage: float = 0.0015         # işlem başı kayma varsayımı
    max_positions: int = 5
    risk_per_trade: float = 0.01     # işlem başına özsermayenin %1'i risk
    max_position_pct: float = 0.25   # tek hisse en fazla %25
    atr_stop_mult: float = 2.5       # ilk stop = giriş - 2.5*ATR
    trail_mult: float = 3.5          # takip eden stop = zirve - 3.5*ATR
    cooldown_days: int = 5           # stop sonrası bekleme
    # --- sinyal ---
    fast: int = 20
    slow: int = 50
    trend: int = 200
    rsi_len: int = 14
    rsi_buy_max: float = 75
    adx_min: float = 20
    breakout_len: int = 20
    rank_len: int = 90               # momentum sıralaması
    min_score: int = 5               # 6 koşuldan en az kaçı sağlanmalı
    min_turnover: float = 20_000_000  # 20 günlük ort. TL hacim alt sınırı
    regime_filter: bool = True       # endeks düşüş trendindeyse yeni alım yok
    regime_len: int = 100
    annual_inflation: Optional[float] = None  # reel getiri göstermek için
