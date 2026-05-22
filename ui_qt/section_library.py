"""Section and material library for StructLab.

Provides:
  - MATERIALS dict: name → (E in Pa, label)
  - STEEL_PROFILES dict: series → list of (name, A in m², I in m⁴)
  - concrete_section(b, h) → (A, I)
  - t_beam_section(bf, hf, bw, hw) → (A, I)
  - circular_section(d) → (A, I)
  - hollow_rect_section(b, h, t) → (A, I)
"""

from __future__ import annotations
import math

# ── Materials ─────────────────────────────────────────────────────────────────

MATERIALS: dict[str, tuple[float, str]] = {
    # name: (E in Pa, display label)   — ordered S275 first (most common EU structural steel)
    "Steel S275":    (210e9, "E = 210 GPa  |  EN 1993-1-1"),
    "Steel S235":    (210e9, "E = 210 GPa  |  EN 1993-1-1"),
    "Steel S355":    (210e9, "E = 210 GPa  |  EN 1993-1-1"),
    "Steel S460":    (210e9, "E = 210 GPa  |  EN 1993-1-1"),
    "Concrete C20/25": ( 29e9, "Ecm = 29 GPa  |  EN 1992-1-1"),
    "Concrete C25/30": ( 30e9, "Ecm = 30 GPa  |  EN 1992-1-1"),
    "Concrete C30/37": ( 32e9, "Ecm = 32 GPa  |  EN 1992-1-1"),
    "Concrete C35/45": ( 34e9, "Ecm = 34 GPa  |  EN 1992-1-1"),
    "Concrete C40/50": ( 35e9, "Ecm = 35 GPa  |  EN 1992-1-1"),
    "Timber GL24h":    ( 11.5e9, "E₀,mean = 11.5 GPa  |  EN 1995"),
    "Timber GL28h":    ( 12.6e9, "E₀,mean = 12.6 GPa  |  EN 1995"),
    "Aluminium":       ( 70e9,   "E = 70 GPa  |  EN 1999"),
    "Custom":          (210e9,   "Enter E manually"),
}

# ── Steel profiles ────────────────────────────────────────────────────────────
# Each entry: (profile_name, A_m2, Iy_m4)
# Data sourced from standard Euronorm tables (rounded to 4 significant figures).

def _ipe() -> list[tuple[str, float, float]]:
    # IPE series (European I-beams) — strong axis Iy
    data = [
        ("IPE 80",   764e-6,  80.1e-8),
        ("IPE 100",  1032e-6, 171e-8),
        ("IPE 120",  1321e-6, 318e-8),
        ("IPE 140",  1643e-6, 541e-8),
        ("IPE 160",  2009e-6, 869e-8),
        ("IPE 180",  2395e-6, 1317e-8),
        ("IPE 200",  2848e-6, 1943e-8),
        ("IPE 220",  3337e-6, 2772e-8),
        ("IPE 240",  3912e-6, 3892e-8),
        ("IPE 270",  4595e-6, 5790e-8),
        ("IPE 300",  5381e-6, 8356e-8),
        ("IPE 330",  6261e-6, 11770e-8),
        ("IPE 360",  7273e-6, 16270e-8),
        ("IPE 400",  8446e-6, 23130e-8),
        ("IPE 450",  9882e-6, 33740e-8),
        ("IPE 500",  11550e-6, 48200e-8),
        ("IPE 550",  13440e-6, 67120e-8),
        ("IPE 600",  15600e-6, 92080e-8),
    ]
    return [(n, A, I) for n, A, I in data]


def _hea() -> list[tuple[str, float, float]]:
    data = [
        ("HEA 100",  2124e-6, 349.2e-8),
        ("HEA 120",  2534e-6, 606.2e-8),
        ("HEA 140",  3142e-6, 1033e-8),
        ("HEA 160",  3877e-6, 1673e-8),
        ("HEA 180",  4525e-6, 2510e-8),
        ("HEA 200",  5383e-6, 3692e-8),
        ("HEA 220",  6434e-6, 5410e-8),
        ("HEA 240",  7684e-6, 7763e-8),
        ("HEA 260",  8682e-6, 10450e-8),
        ("HEA 280",  9726e-6, 13670e-8),
        ("HEA 300",  11250e-6, 18260e-8),
        ("HEA 320",  12400e-6, 22930e-8),
        ("HEA 340",  13300e-6, 27690e-8),
        ("HEA 360",  14250e-6, 33090e-8),
        ("HEA 400",  15900e-6, 45070e-8),
        ("HEA 450",  17800e-6, 63720e-8),
        ("HEA 500",  19780e-6, 86970e-8),
        ("HEA 550",  21190e-6, 111900e-8),
        ("HEA 600",  22600e-6, 141200e-8),
    ]
    return [(n, A, I) for n, A, I in data]


def _heb() -> list[tuple[str, float, float]]:
    data = [
        ("HEB 100",  2600e-6, 449.5e-8),
        ("HEB 120",  3400e-6, 864.4e-8),
        ("HEB 140",  4296e-6, 1509e-8),
        ("HEB 160",  5425e-6, 2492e-8),
        ("HEB 180",  6525e-6, 3831e-8),
        ("HEB 200",  7808e-6, 5696e-8),
        ("HEB 220",  9104e-6, 8091e-8),
        ("HEB 240",  10600e-6, 11260e-8),
        ("HEB 260",  11840e-6, 14920e-8),
        ("HEB 280",  13140e-6, 19270e-8),
        ("HEB 300",  14900e-6, 25170e-8),
        ("HEB 320",  16130e-6, 30820e-8),
        ("HEB 340",  17090e-6, 36660e-8),
        ("HEB 360",  18060e-6, 43190e-8),
        ("HEB 400",  19780e-6, 57680e-8),
        ("HEB 450",  21800e-6, 79890e-8),
        ("HEB 500",  23860e-6, 107200e-8),
        ("HEB 550",  25400e-6, 136700e-8),
        ("HEB 600",  27000e-6, 171000e-8),
    ]
    return [(n, A, I) for n, A, I in data]


def _chs() -> list[tuple[str, float, float]]:
    """Circular Hollow Section — OD × thickness (mm)."""
    data = [
        ("CHS 48.3×3",   420e-6,   12.2e-8),
        ("CHS 60.3×4",   700e-6,   29.1e-8),
        ("CHS 76.1×4",   904e-6,   60.1e-8),
        ("CHS 88.9×4",  1060e-6,   95.7e-8),
        ("CHS 101.6×5", 1510e-6,  181e-8),
        ("CHS 114.3×5", 1710e-6,  261e-8),
        ("CHS 139.7×5", 2110e-6,  481e-8),
        ("CHS 168.3×6", 3050e-6,  999e-8),
        ("CHS 193.7×6", 3520e-6,  1520e-8),
        ("CHS 219.1×8", 5350e-6,  2840e-8),
        ("CHS 244.5×8", 5990e-6,  3940e-8),
        ("CHS 273.0×8", 6700e-6,  5500e-8),
        ("CHS 323.9×10", 9990e-6, 11300e-8),
        ("CHS 355.6×10", 11000e-6, 15200e-8),
        ("CHS 406.4×10", 12600e-6, 22700e-8),
    ]
    return [(n, A, I) for n, A, I in data]


def _rhs() -> list[tuple[str, float, float]]:
    """Rectangular Hollow Section — b×h×t (mm)."""
    data = [
        ("RHS 60×40×4",    720e-6,  23.6e-8),
        ("RHS 80×60×4",   1080e-6,  64.7e-8),
        ("RHS 100×60×5",  1480e-6,  107e-8),
        ("RHS 120×80×5",  1880e-6,  231e-8),
        ("RHS 150×100×6", 2820e-6,  613e-8),
        ("RHS 200×100×8", 4480e-6,  1340e-8),
        ("RHS 200×150×8", 5440e-6,  2480e-8),
        ("RHS 250×150×8", 6240e-6,  4140e-8),
        ("RHS 300×200×10",9600e-6,  10200e-8),
        ("RHS 400×200×12",14000e-6, 24800e-8),
    ]
    return [(n, A, I) for n, A, I in data]


STEEL_PROFILES: dict[str, list[tuple[str, float, float]]] = {
    "IPE":  _ipe(),
    "HEA":  _hea(),
    "HEB":  _heb(),
    "CHS":  _chs(),
    "RHS":  _rhs(),
}

# ── Geometry helpers ──────────────────────────────────────────────────────────

def rectangular_section(b: float, h: float) -> tuple[float, float]:
    """Return (A, I) for a solid rectangle b×h (metres)."""
    return b * h, b * h**3 / 12


def t_beam_section(bf: float, hf: float, bw: float, hw: float) -> tuple[float, float]:
    """Return (A, I_centroid) for a T-beam (flange bf×hf on top, web bw×hw).

    All dimensions in metres. I computed about the centroid of the composite.
    """
    A_f = bf * hf
    A_w = bw * hw
    A   = A_f + A_w
    y_f = hw + hf / 2    # centroid of flange from bottom of web
    y_w = hw / 2
    y_c = (A_f * y_f + A_w * y_w) / A   # centroid from bottom
    I_f = bf * hf**3 / 12 + A_f * (y_f - y_c)**2
    I_w = bw * hw**3 / 12 + A_w * (y_w - y_c)**2
    return A, I_f + I_w


def circular_section(d: float) -> tuple[float, float]:
    """Return (A, I) for a solid circle of diameter d (metres)."""
    r = d / 2
    return math.pi * r**2, math.pi * r**4 / 4


def hollow_rect_section(b: float, h: float, t: float) -> tuple[float, float]:
    """Return (A, I) for a rectangular hollow section b×h, wall thickness t."""
    A = b * h - (b - 2 * t) * (h - 2 * t)
    I = (b * h**3 - (b - 2 * t) * (h - 2 * t)**3) / 12
    return A, I
