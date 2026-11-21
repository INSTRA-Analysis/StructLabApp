"""Start-page banners of the rotation: the numbers they draw match closed-form results."""

import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


# ── S2 portal frame ──────────────────────────────────────────────────────────

def _kleinlogel_fixed_portal(h, span, w, wind, I_col=1.0, I_beam=1.0):
    """Kleinlogel, fixed-base portal: UDL w on the girder plus horizontal load at eaves level.

    k = (I_beam / I_col)·(h / span); returns |M| at the bases (A, D) and knees (B, C).
    """
    k = (I_beam / I_col) * (h / span)
    n1, n2 = k + 2, 6 * k + 1
    base_g, knee_g = w * span ** 2 / (12 * n1), w * span ** 2 / (6 * n1)
    base_w, knee_w = wind * h * (3 * k + 1) / (2 * n2), wind * h * 3 * k / (2 * n2)
    return (abs(base_g - base_w), abs(base_g + base_w)), (abs(knee_g - knee_w), abs(knee_g + knee_w))


def test_portal_matches_kleinlogel_closed_form():
    from ui_qt.banner_gallery import solve_portal
    sol = solve_portal(h=4.0, span=6.0, w=1.0, wind=2.0, EA=1e7)      # near-inextensible members
    (base_a, base_d), (knee_b, knee_c) = _kleinlogel_fixed_portal(4.0, 6.0, 1.0, 2.0)
    assert sol.base_moments == pytest.approx((base_a, base_d), rel=1e-4)
    assert sol.knee_moments == pytest.approx((knee_b, knee_c), rel=1e-4)


def test_portal_is_in_equilibrium_and_symmetric_without_wind():
    from ui_qt.banner_gallery import solve_portal
    sym = solve_portal(wind=0.0)
    assert sym.base_moments[0] == pytest.approx(sym.base_moments[1], rel=1e-9)
    assert sym.knee_moments[0] == pytest.approx(sym.knee_moments[1], rel=1e-9)
    sol = solve_portal()
    # column shears V = (M_top + M_bottom) / h with end moments in local sign: they carry W
    shears = [(m.m_i + m.m_j) / m.length for m in (sol.members[0], sol.members[2])]
    assert abs(sum(shears)) == pytest.approx(2.0, rel=1e-6)
    # rafter moment at midspan from the member: end moments plus wL²/8
    rafter = sol.members[1]
    assert rafter.moment(0.5) == pytest.approx(
        -rafter.m_i / 2 + rafter.m_j / 2 + 6.0 ** 2 / 8, rel=1e-12)


# ── D1 mode shapes ───────────────────────────────────────────────────────────

def test_shear_frame_modes_are_the_textbook_eigenvectors():
    from ui_qt.banner_gallery import shear_frame_modes
    values, modes = shear_frame_modes(3)
    assert values == pytest.approx([0.198062, 1.554958, 3.246980], abs=1e-6)
    assert modes[:, 0] == pytest.approx([0.445042, 0.801938, 1.0], abs=1e-6)
    assert modes[:, 1] == pytest.approx([1.0, 0.445042, -0.801938], abs=1e-6)
    assert modes[:, 2] == pytest.approx([0.801938, -1.0, 0.445042], abs=1e-6)
    K = np.array([[2, -1, 0], [-1, 2, -1], [0, -1, 1.0]])
    for k in range(3):                                        # K φ = λ φ
        assert K @ modes[:, k] == pytest.approx(values[k] * modes[:, k], abs=1e-9)


# ── X1 effective lengths ─────────────────────────────────────────────────────

def test_fixed_pinned_column_root_and_effective_length():
    from ui_qt.banner_gallery import fixed_pinned_root, column_shapes
    kl = fixed_pinned_root()
    assert kl == pytest.approx(4.493409, abs=1e-6)
    assert np.tan(kl) == pytest.approx(kl, rel=1e-9)
    factors = {name: K for name, K, *_ in column_shapes()}
    assert factors == pytest.approx({"pinned–pinned": 1.0, "fixed–free": 2.0,
                                     "fixed–pinned": 0.6992, "fixed–fixed": 0.5}, abs=1e-4)


def test_buckled_shapes_satisfy_their_end_conditions():
    from ui_qt.banner_gallery import column_shapes
    h = 1e-5
    d1 = lambda f, s: (f(s + h) - f(s - h)) / (2 * h)
    d2 = lambda f, s: (f(s + h) - 2 * f(s) + f(s - h)) / (h * h)
    for name, _K, f, bottom, top in column_shapes():
        assert f(0.0) == pytest.approx(0.0, abs=1e-9), name                  # no base movement
        if bottom == "fixed":
            assert d1(f, 0.0 + h) == pytest.approx(0.0, abs=1e-3), name      # no base rotation
        if top == "pin":
            assert f(1.0) == pytest.approx(0.0, abs=1e-9), name              # no top movement
            assert d2(f, 1.0 - h) == pytest.approx(0.0, abs=2e-2), name      # no top moment
        if top == "fixed":
            assert f(1.0) == pytest.approx(0.0, abs=1e-9), name
            assert d1(f, 1.0 - h) == pytest.approx(0.0, abs=1e-3), name
        if top == "free":
            assert d2(f, 1.0 - h) == pytest.approx(0.0, abs=2e-2), name      # no tip moment


# ── R2 reliability index ─────────────────────────────────────────────────────

def test_reliability_index_and_design_point():
    from math import erfc, sqrt
    from ui_qt.banner_gallery import ReliabilityProblem
    pr = ReliabilityProblem()
    assert pr.beta == pytest.approx(0.9 / 0.25)
    assert pr.pf == pytest.approx(0.5 * erfc(3.6 / sqrt(2)), rel=1e-12)
    assert pr.pf == pytest.approx(1.5911e-4, rel=1e-3)
    ur, us = pr.design_point
    assert pr.g(ur, us) == pytest.approx(0.0, abs=1e-12)                     # on the limit state
    assert np.hypot(ur, us) == pytest.approx(pr.beta, rel=1e-12)             # at distance β
    for u in np.linspace(-10, 10, 201):                                       # and the closest point
        assert np.hypot(u, pr.limit_u_s(u)) >= pr.beta - 1e-9


# ── every banner draws at every step ─────────────────────────────────────────

def test_each_banner_paints_every_frame_of_its_draw_in(qapp):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QImage, QPainter
    from ui_qt import banner_themes as bt
    for entry in bt.BANNERS:
        art = entry.make()
        for step in (0, art.steps // 2, art.steps):
            img = QImage(480, 150, QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(0)
            p = QPainter(img)
            art.paint(p, QPointF(0, 0), step)
            p.end()
        assert art.theme
