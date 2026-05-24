"""Section and material library for StructLab.

Provides:
  - MATERIALS dict: name → (E in Pa, density kg/m³, fy/fck Pa, mat_type, label)
  - STEEL_PROFILES dict: series → list of (name, A in m², I in m⁴, W_pl in m³, W_el in m³)
    W_pl is the plastic section modulus (strong axis) used for EC3 utilization checks.
    W_el is the elastic section modulus (strong axis) used for elastic fibre stress σ = M/W_el.
  - concrete_section(b, h) → (A, I)
  - t_beam_section(bf, hf, bw, hw) → (A, I)
  - circular_section(d) → (A, I)
  - hollow_rect_section(b, h, t) → (A, I)
"""

from __future__ import annotations
import math

# ── Materials ─────────────────────────────────────────────────────────────────
# Each entry: (E in Pa, density in kg/m³, characteristic strength in Pa,
#              mat_type ("steel"/"concrete"/"timber"), display label)
# mat_type controls which design-check fields are shown in the Design tab.

MATERIALS: dict[str, tuple[float, float, float, str, str]] = {
    # Steel grades — EN 10025-2, fy for t ≤ 16 mm
    "Steel S235":      (210e9, 7850, 235e6, "steel",    "E = 210 GPa  |  fy = 235 MPa  |  EN 1993"),
    "Steel S275":      (210e9, 7850, 275e6, "steel",    "E = 210 GPa  |  fy = 275 MPa  |  EN 1993"),
    "Steel S355":      (210e9, 7850, 355e6, "steel",    "E = 210 GPa  |  fy = 355 MPa  |  EN 1993"),
    "Steel S420":      (210e9, 7850, 420e6, "steel",    "E = 210 GPa  |  fy = 420 MPa  |  EN 1993"),
    "Steel S460":      (210e9, 7850, 460e6, "steel",    "E = 210 GPa  |  fy = 460 MPa  |  EN 1993"),
    # Concrete grades — EN 1992-1-1, cylinder strength fck
    "Concrete C20/25": ( 29e9, 2500,  20e6, "concrete", "Ecm = 29 GPa  |  fck = 20 MPa  |  EN 1992"),
    "Concrete C25/30": ( 30e9, 2500,  25e6, "concrete", "Ecm = 30 GPa  |  fck = 25 MPa  |  EN 1992"),
    "Concrete C30/37": ( 32e9, 2500,  30e6, "concrete", "Ecm = 32 GPa  |  fck = 30 MPa  |  EN 1992"),
    "Concrete C35/45": ( 34e9, 2500,  35e6, "concrete", "Ecm = 34 GPa  |  fck = 35 MPa  |  EN 1992"),
    "Concrete C40/50": ( 35e9, 2500,  40e6, "concrete", "Ecm = 35 GPa  |  fck = 40 MPa  |  EN 1992"),
    # Glulam timber — EN 1995, bending strength fm,k
    "Timber GL24h":    (11.5e9,  500,  24e6, "timber",  "E₀,mean = 11.5 GPa  |  fm,k = 24 MPa  |  EN 1995"),
    "Timber GL28h":    (12.6e9,  500,  28e6, "timber",  "E₀,mean = 12.6 GPa  |  fm,k = 28 MPa  |  EN 1995"),
    # Aluminium — EN 1999, 6082-T6 0.2% proof stress
    "Aluminium":       ( 70e9,  2700, 260e6, "steel",   "E = 70 GPa  |  f0.2 = 260 MPa  |  EN 1999"),
    # Custom — all values entered manually
    "Custom":          (210e9,     0,   0.0, "steel",   "Enter E, density and strength manually"),
}

# ── Steel profiles ────────────────────────────────────────────────────────────
# Each entry: (profile_name, A_m2, Iy_m4, W_pl_m3, W_el_m3)
# W_pl = plastic section modulus (strong axis), W_el = elastic section modulus.
# W_el = I / y_max = 2*I / h  (y_max = h/2 for symmetric sections).
# Data sourced from standard Euronorm / ArcelorMittal tables (rounded to 4 sig figs).

def _ipe() -> list[tuple[str, float, float, float, float]]:
    # IPE series — h = nominal depth; W_el = 2*I/h (strong axis)
    data = [
        ("IPE 80",    764e-6,   80.1e-8,   23.2e-6,  20.0e-6),
        ("IPE 100",  1032e-6,  171e-8,    39.4e-6,  34.2e-6),
        ("IPE 120",  1321e-6,  318e-8,    60.7e-6,  53.0e-6),
        ("IPE 140",  1643e-6,  541e-8,    88.3e-6,  77.3e-6),
        ("IPE 160",  2009e-6,  869e-8,   123e-6,   109e-6),
        ("IPE 180",  2395e-6, 1317e-8,   166e-6,   146e-6),
        ("IPE 200",  2848e-6, 1943e-8,   221e-6,   194e-6),
        ("IPE 220",  3337e-6, 2772e-8,   285e-6,   252e-6),
        ("IPE 240",  3912e-6, 3892e-8,   367e-6,   324e-6),
        ("IPE 270",  4595e-6, 5790e-8,   484e-6,   429e-6),
        ("IPE 300",  5381e-6, 8356e-8,   628e-6,   557e-6),
        ("IPE 330",  6261e-6, 11770e-8,  804e-6,   713e-6),
        ("IPE 360",  7273e-6, 16270e-8, 1019e-6,   904e-6),
        ("IPE 400",  8446e-6, 23130e-8, 1307e-6,  1157e-6),
        ("IPE 450",  9882e-6, 33740e-8, 1702e-6,  1499e-6),
        ("IPE 500", 11550e-6, 48200e-8, 2194e-6,  1928e-6),
        ("IPE 550", 13440e-6, 67120e-8, 2787e-6,  2441e-6),
        ("IPE 600", 15600e-6, 92080e-8, 3512e-6,  3069e-6),
    ]
    return data


def _hea() -> list[tuple[str, float, float, float, float]]:
    # HEA series — actual depth h (mm) from ArcelorMittal tables; W_el = 2*I/h_actual
    data = [
        ("HEA 100",  2124e-6,  349.2e-8,   83.9e-6,  72.8e-6),   # h=96 mm
        ("HEA 120",  2534e-6,  606.2e-8,   120e-6,   106e-6),    # h=114 mm
        ("HEA 140",  3142e-6, 1033e-8,    173e-6,   155e-6),    # h=133 mm
        ("HEA 160",  3877e-6, 1673e-8,    245e-6,   220e-6),    # h=152 mm
        ("HEA 180",  4525e-6, 2510e-8,    325e-6,   294e-6),    # h=171 mm
        ("HEA 200",  5383e-6, 3692e-8,    429e-6,   389e-6),    # h=190 mm
        ("HEA 220",  6434e-6, 5410e-8,    568e-6,   515e-6),    # h=210 mm
        ("HEA 240",  7684e-6, 7763e-8,    745e-6,   675e-6),    # h=230 mm
        ("HEA 260",  8682e-6, 10450e-8,   919e-6,   836e-6),    # h=250 mm
        ("HEA 280",  9726e-6, 13670e-8,  1112e-6,  1013e-6),    # h=270 mm
        ("HEA 300", 11250e-6, 18260e-8,  1383e-6,  1259e-6),    # h=290 mm
        ("HEA 320", 12400e-6, 22930e-8,  1628e-6,  1479e-6),    # h=310 mm
        ("HEA 340", 13300e-6, 27690e-8,  1852e-6,  1679e-6),    # h=330 mm
        ("HEA 360", 14250e-6, 33090e-8,  2088e-6,  1891e-6),    # h=350 mm
        ("HEA 400", 15900e-6, 45070e-8,  2562e-6,  2311e-6),    # h=390 mm
        ("HEA 450", 17800e-6, 63720e-8,  3216e-6,  2896e-6),    # h=440 mm
        ("HEA 500", 19780e-6, 86970e-8,  3949e-6,  3549e-6),    # h=490 mm
        ("HEA 550", 21190e-6, 111900e-8, 4622e-6,  4144e-6),    # h=540 mm
        ("HEA 600", 22600e-6, 141200e-8, 5350e-6,  4786e-6),    # h=590 mm
    ]
    return data


def _heb() -> list[tuple[str, float, float, float, float]]:
    # HEB series — h = nominal depth; W_el = 2*I/h (strong axis)
    data = [
        ("HEB 100",  2600e-6,  449.5e-8,   104e-6,   89.9e-6),
        ("HEB 120",  3400e-6,  864.4e-8,   165e-6,   144e-6),
        ("HEB 140",  4296e-6, 1509e-8,    245e-6,   216e-6),
        ("HEB 160",  5425e-6, 2492e-8,    354e-6,   312e-6),
        ("HEB 180",  6525e-6, 3831e-8,    481e-6,   426e-6),
        ("HEB 200",  7808e-6, 5696e-8,    642e-6,   570e-6),
        ("HEB 220",  9104e-6, 8091e-8,    827e-6,   736e-6),
        ("HEB 240", 10600e-6, 11260e-8,  1053e-6,   938e-6),
        ("HEB 260", 11840e-6, 14920e-8,  1283e-6,  1148e-6),
        ("HEB 280", 13140e-6, 19270e-8,  1534e-6,  1376e-6),
        ("HEB 300", 14900e-6, 25170e-8,  1869e-6,  1678e-6),
        ("HEB 320", 16130e-6, 30820e-8,  2149e-6,  1926e-6),
        ("HEB 340", 17090e-6, 36660e-8,  2408e-6,  2157e-6),
        ("HEB 360", 18060e-6, 43190e-8,  2683e-6,  2399e-6),
        ("HEB 400", 19780e-6, 57680e-8,  3232e-6,  2884e-6),
        ("HEB 450", 21800e-6, 79890e-8,  3982e-6,  3551e-6),
        ("HEB 500", 23860e-6, 107200e-8, 4815e-6,  4288e-6),
        ("HEB 550", 25400e-6, 136700e-8, 5591e-6,  4971e-6),
        ("HEB 600", 27000e-6, 171000e-8, 6425e-6,  5700e-6),
    ]
    return data


def _chs() -> list[tuple[str, float, float, float, float]]:
    """Circular Hollow Section — OD × thickness (mm).
    W_pl = (D³ - (D-2t)³) / 6  [m³]
    W_el = 2*I / D              [m³]  (= π*(D⁴-di⁴) / (32 * D/2))
    """
    data = [
        ("CHS 48.3×3",    420e-6,  12.2e-8,    6.17e-6,   5.05e-6),
        ("CHS 60.3×4",    700e-6,  29.1e-8,   12.70e-6,   9.65e-6),
        ("CHS 76.1×4",    904e-6,  60.1e-8,   20.82e-6,  15.79e-6),
        ("CHS 88.9×4",   1060e-6,  95.7e-8,   28.81e-6,  21.54e-6),
        ("CHS 101.6×5",  1510e-6,  181e-8,    46.69e-6,  35.63e-6),
        ("CHS 114.3×5",  1710e-6,  261e-8,    59.77e-6,  45.67e-6),
        ("CHS 139.7×5",  2110e-6,  481e-8,    90.90e-6,  68.87e-6),
        ("CHS 168.3×6",  3050e-6,  999e-8,   157.82e-6, 118.8e-6),
        ("CHS 193.7×6",  3520e-6, 1520e-8,   211.83e-6, 157.0e-6),
        ("CHS 219.1×8",  5350e-6, 2840e-8,   355.78e-6, 259.3e-6),
        ("CHS 244.5×8",  5990e-6, 3940e-8,   447.38e-6, 322.5e-6),
        ("CHS 273.0×8",  6700e-6, 5500e-8,   561.97e-6, 403.0e-6),
        ("CHS 323.9×10", 9990e-6, 11300e-8,  983.83e-6, 697.7e-6),
        ("CHS 355.6×10", 11000e-6, 15200e-8, 1195.59e-6, 855.0e-6),
        ("CHS 406.4×10", 12600e-6, 22700e-8, 1567.26e-6, 1118e-6),
    ]
    return data


def _rhs() -> list[tuple[str, float, float, float, float]]:
    """Rectangular Hollow Section — b×h×t (mm).
    W_pl,y = (b_max × h_max² - (b_max-2t)(h_max-2t)²) / 4  [m³, strong axis]
    W_el,y = 2*I / h_max                                     [m³, strong axis]
    """
    data = [
        ("RHS 60×40×4",     720e-6,   23.6e-8,   14.37e-6,   7.87e-6),
        ("RHS 80×60×4",    1080e-6,   64.7e-8,   28.61e-6,  16.18e-6),
        ("RHS 100×60×5",   1480e-6,  107e-8,    48.75e-6,  21.40e-6),
        ("RHS 120×80×5",   1880e-6,  231e-8,    76.25e-6,  38.50e-6),
        ("RHS 150×100×6",  2820e-6,  613e-8,   143.53e-6,  81.73e-6),
        ("RHS 200×100×8",  4480e-6, 1340e-8,   289.02e-6, 134.0e-6),
        ("RHS 200×150×8",  5440e-6, 2480e-8,   365.82e-6, 248.0e-6),
        ("RHS 250×150×8",  6240e-6, 4140e-8,   509.42e-6, 331.2e-6),
        ("RHS 300×200×10", 9600e-6, 10200e-8,  972.00e-6, 680.0e-6),
        ("RHS 400×200×12", 14000e-6, 24800e-8, 1779.46e-6, 1240e-6),
    ]
    return data


STEEL_PROFILES: dict[str, list[tuple[str, float, float, float, float]]] = {
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
