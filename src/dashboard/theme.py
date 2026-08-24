"""Accessible dashboard palette and carrier identity."""

AERO_BLUE = "#0B3A66"
AERO_BLUE_LIGHT = "#DCEAF5"
MAGENTA = "#B4236C"
GOLD = "#9A6B00"
ORANGE = "#B04D16"
OLIVE = "#66752A"
INK = "#17212B"
MUTED = "#5E6B78"
GRID = "#D9E0E7"
PAPER = "#F7F9FB"
WHITE = "#FFFFFF"

CARRIER_COLORS = {
    "AEROMEXICO": AERO_BLUE,
    "VOLARIS": MAGENTA,
    "VIVA_AEROBUS": OLIVE,
    "DELTA": ORANGE,
    "RYANAIR": GOLD,
    "MARKET_TOTAL_MX": MUTED,
}

CHART_LAYOUT = {
    "paper_bgcolor": WHITE,
    "plot_bgcolor": WHITE,
    "font": {"family": "Inter, Segoe UI, sans-serif", "color": INK},
    "margin": {"l": 48, "r": 24, "t": 62, "b": 48},
    "hovermode": "x unified",
}
