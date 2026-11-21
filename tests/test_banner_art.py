"""Start-page banner art: the truss stiffness matrix it shows is a correct assembly."""

import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def test_pratt_truss_assembly_is_a_valid_stiffness_matrix():
    from ui_qt.banner_art import ASSEMBLY as a
    assert len(a.nodes) == 16 and len(a.bars) == 29 and a.n_dof == 32
    assert np.allclose(a.K, a.K.T)
    # A free plane truss has exactly 3 rigid-body modes (2 translations, 1 rotation)
    eig = np.linalg.eigvalsh(a.K)
    assert np.sum(np.abs(eig) < 1e-9) == 3 and np.all(eig > -1e-9)
    # Banded thanks to the left-to-right numbering
    rows, cols = np.nonzero(np.abs(a.K) > 1e-12)
    assert np.max(np.abs(rows - cols)) == 7


def test_pin_and_roller_make_it_solvable_with_the_textbook_chord_force():
    """Same model as the picture: P down at every bottom node, max chord force 8P·a/h."""
    from ui_qt.banner_art import ASSEMBLY as a, DEPTH
    n = a.n_dof
    F = np.zeros(n)
    bottom = [i for i, (x, y) in enumerate(a.nodes) if y == 0 and 0 < x < 8]
    F[[2 * i + 1 for i in bottom]] = -1.0
    right = next(i for i, (x, y) in enumerate(a.nodes) if x == 8)
    free = [d for d in range(n) if d not in (0, 1, 2 * right + 1)]
    d = np.zeros(n)
    d[free] = np.linalg.solve(a.K[np.ix_(free, free)], F[free])
    forces = []
    for i, j in a.bars:
        delta = a.nodes[j] - a.nodes[i]
        forces.append(np.dot(d[[2 * j, 2 * j + 1]] - d[[2 * i, 2 * i + 1]], delta) / np.dot(delta, delta))
    assert max(abs(f) for f in forces) == pytest.approx(8 / DEPTH)


def test_matrix_cells_cover_exactly_the_non_zero_terms(qapp):
    from ui_qt.banner_art import ASSEMBLY as a, cell_colours
    cells = cell_colours(a, len(a.bars))
    assert set(cells) == {(r, c) for r, c in zip(*np.nonzero(np.abs(a.K) > 1e-12))}
    assert len(cell_colours(a, 0)) == 0
    first = cell_colours(a, 1)
    assert set(first) == set(a.blocks[0])                    # one member = one 4 × 4 block


def test_typeset_frame_matrix_is_the_solvers_frame_element():
    """The banner's kᵉ, evaluated with numbers, equals elements.FrameElement's local k."""
    from core.material import Material
    from core.node import Node
    from core.section import Section
    from elements.frame_element import FrameElement
    from ui_qt.banner_art import FRAME_TERMS, evaluate_frame_term
    E, A, I, L = 210e9, 5.38e-3, 8.356e-5, 4.5
    el = FrameElement(1, Node(1, 0.0, 0.0), Node(2, L, 0.0), Material("S355", E),
                      Section(name="IPE 300", area=A, moment_of_inertia=I))
    k_solver = el.local_stiffness_matrix()
    k_banner = np.array([[evaluate_frame_term(t, E, A, I, L) for t in row] for row in FRAME_TERMS])
    assert k_solver.shape == (6, 6)
    assert np.allclose(k_banner, k_solver, rtol=1e-12, atol=0.0)


def test_stress_trajectories_stay_in_the_beam_and_cover_both_families():
    from ui_qt.banner_art import stress_trajectories
    paths = stress_trajectories()
    assert {family for family, _ in paths} == {0, 1}
    for family, pts in paths:
        assert len(pts) > 20
        assert np.all(pts[:, 0] >= 0) and np.all(pts[:, 0] <= 6)
        assert np.all(np.abs(pts[:, 1]) <= 0.5)
        assert pts[0, 0] == pytest.approx(3.0)              # traced out from midspan
        # tension starts below the neutral axis, compression above
        assert (pts[0, 1] < 0) == (family == 0)


def test_banner_draws_in_once_then_rests_complete(qapp):
    from ui_qt.welcome_dialog import _Banner
    b = _Banner()
    b.resize(1000, 150)
    b.show()
    qapp.processEvents()
    assert b._timer.isActive() and b.count < b._steps         # started on first show
    for _ in range(b._steps):
        b._step()
    assert b.count == b._steps and not b._timer.isActive()
    assert not b.grab().isNull()
    b.hide(); b.show()
    assert not b._timer.isActive()                            # plays only once by itself
    b.play()
    assert b.count == 0 and b._timer.isActive()               # click / replay
    b._timer.stop()
    b.close()
