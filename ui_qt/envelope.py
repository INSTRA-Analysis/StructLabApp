"""Envelope results dialog: max/min across all solved EN 1990 combinations.

solve_runs_rich is a list of dicts, each with:
  'combo'          — LoadCombination
  'displacements'  — numpy array, index [node.id * 3 + dof], dof 0=dx 1=dy 2=θ
  'member_results' — list[ElementResult], one per UI member (aggregated ends)
  'sub_results'    — list[ElementResult], one per sub-element (for sampling)
  'member_el_map'  — list[list[int]], member_el_map[i] = sub-element IDs for member i
"""

from __future__ import annotations

import math

import numpy as np
from matplotlib.figure import Figure
from matplotlib.patches import Patch

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QDialogButtonBox,
    QAbstractItemView, QWidget, QDoubleSpinBox,
)
from PyQt6.QtCore import Qt

from ui_qt.model_state import ModelState


# ── helpers ────────────────────────────────────────────────────────────────────

def _cell(text: str, center: bool = False) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    if center:
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _style_table(tbl: QTableWidget) -> None:
    tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tbl.setAlternatingRowColors(True)
    tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    hh = tbl.horizontalHeader()
    hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    hh.setStretchLastSection(True)


# ── point-wise sampling ────────────────────────────────────────────────────────

def _sample_member(sub_results: list, el_ids: list[int],
                   n_per_sub: int = 8) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (x_norm, M_Nm, V_N) sampled along one UI member.

    x_norm is in [0, 1].  M and V are linearly interpolated between sub-element
    end forces — accurate to O(L_sub²) with the default n_sub=10 discretisation.
    """
    res_map = {r.element_id: r for r in sub_results}
    n_sub = len(el_ids)
    n_pts = n_per_sub * n_sub + 1

    x_norm = np.linspace(0.0, 1.0, n_pts)
    M_arr  = np.empty(n_pts)
    V_arr  = np.empty(n_pts)

    for i, x in enumerate(x_norm):
        k = min(int(x * n_sub), n_sub - 1)
        t = x * n_sub - k
        r = res_map[el_ids[k]]
        M_arr[i] = r.M_i + t * (r.M_j - r.M_i)
        # V_j is the upward force on the right node; internal shear at right end = −V_j
        V_arr[i] = (1.0 - t) * r.V_i - t * r.V_j

    return x_norm, M_arr, V_arr


# ── envelope plotting ──────────────────────────────────────────────────────────

def _draw_envelope_on_ax(ax, solve_runs_rich: list, state: ModelState,
                         kind: str = 'M', scale_mult: float = 1.0) -> None:
    """Draw BMD or SFD envelope on a Matplotlib Axes in model coordinates.

    Perpendicular draw direction: (dy/L, -dx/L) — CW rotation of the member
    so that positive M (sagging) appears below a horizontal baseline, matching
    the canvas overlay convention.

    kind: 'M' → moment envelope,  'V' → shear envelope
    """
    node_map = {nd.id: nd for nd in state.nodes}

    # ── structure geometry ────────────────────────────────────────────────────
    for md in state.members:
        ni, nj = node_map[md.node_i], node_map[md.node_j]
        ax.plot([ni.x, nj.x], [ni.y, nj.y], color='#222222', lw=2.0, zorder=5)
    for nd in state.nodes:
        ax.plot(nd.x, nd.y, 'ko', ms=4, zorder=6)

    if not state.members or not solve_runs_rich:
        return

    max_L = max(
        math.hypot(node_map[md.node_j].x - node_map[md.node_i].x,
                   node_map[md.node_j].y - node_map[md.node_i].y)
        for md in state.members
    )

    # ── first pass: compute envelope data and global max ──────────────────────
    member_envs = []
    global_max_abs = 0.0

    for i, md in enumerate(state.members):
        ni = node_map[md.node_i]; nj = node_map[md.node_j]
        dx = nj.x - ni.x;  dy = nj.y - ni.y
        L  = math.hypot(dx, dy)
        if L < 1e-9:
            continue

        # CW rotation of member direction → positive M offsets below horizontal member
        perp = np.array([dy / L, -dx / L])

        env_max = None;  env_min = None;  x_norm = None

        for run in solve_runs_rich:
            el_ids = run['member_el_map'][i]
            x, M, V = _sample_member(run['sub_results'], el_ids)
            vals = M if kind == 'M' else V

            if x_norm is None:
                x_norm = x;  env_max = vals.copy();  env_min = vals.copy()
            else:
                env_max = np.maximum(env_max, vals)
                env_min = np.minimum(env_min, vals)

        if x_norm is None:
            continue

        global_max_abs = max(global_max_abs,
                             float(np.max(np.abs(env_max))),
                             float(np.max(np.abs(env_min))))

        xs_pt = ni.x + x_norm * dx
        ys_pt = ni.y + x_norm * dy
        member_envs.append((xs_pt, ys_pt, perp, env_max, env_min))

    if global_max_abs < 1e-12:
        ax.text(0.5, 0.5, "All results ≈ 0",
                transform=ax.transAxes, ha='center', va='center',
                fontsize=12, color='gray')
        return

    scale = (max_L * 0.35 / global_max_abs) * scale_mult

    # ── colours ───────────────────────────────────────────────────────────────
    if kind == 'M':
        c_pos, c_neg = '#e65100', '#1565c0'   # deep orange / dark blue
        lbl_pos, lbl_neg = 'Max M  (sagging +)', 'Min M  (hogging −)'
    else:
        c_pos, c_neg = '#2e7d32', '#6a1b9a'   # dark green / deep purple
        lbl_pos, lbl_neg = 'Max V (+)', 'Min V (−)'

    # ── second pass: draw ─────────────────────────────────────────────────────
    for xs_pt, ys_pt, perp, env_max, env_min in member_envs:
        max_x = xs_pt + env_max * scale * perp[0]
        max_y = ys_pt + env_max * scale * perp[1]
        min_x = xs_pt + env_min * scale * perp[0]
        min_y = ys_pt + env_min * scale * perp[1]

        # Max envelope fill + outline
        ax.fill(np.concatenate([xs_pt, max_x[::-1]]),
                np.concatenate([ys_pt, max_y[::-1]]),
                color=c_pos, alpha=0.38, zorder=2)
        ax.plot(max_x, max_y, '-', color=c_pos, lw=1.2, zorder=3)

        # Min envelope fill + outline
        ax.fill(np.concatenate([xs_pt, min_x[::-1]]),
                np.concatenate([ys_pt, min_y[::-1]]),
                color=c_neg, alpha=0.38, zorder=2)
        ax.plot(min_x, min_y, '-', color=c_neg, lw=1.2, zorder=3)

    ax.legend(
        handles=[Patch(color=c_pos, alpha=0.65, label=lbl_pos),
                 Patch(color=c_neg, alpha=0.65, label=lbl_neg)],
        fontsize=9, loc='best', framealpha=0.8,
    )


def _make_plot_tab(solve_runs_rich: list, state: ModelState,
                   kind: str) -> QWidget:
    """Return a QWidget containing a Matplotlib canvas with a scale spinbox."""
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

    w = QWidget()
    vbox = QVBoxLayout(w)
    vbox.setContentsMargins(4, 4, 4, 4)

    # Controls
    hbox = QHBoxLayout()
    lbl = QLabel("Scale ×:")
    spin = QDoubleSpinBox()
    spin.setRange(0.1, 50.0)
    spin.setValue(1.0)
    spin.setSingleStep(0.5)
    spin.setDecimals(1)
    spin.setFixedWidth(75)
    hbox.addWidget(lbl); hbox.addWidget(spin); hbox.addStretch()
    vbox.addLayout(hbox)

    title = ("BMD Envelope — Max/Min Moment across Combinations"
             if kind == 'M' else
             "SFD Envelope — Max/Min Shear across Combinations")

    fig = Figure(figsize=(9, 5), tight_layout=True)
    ax  = fig.add_subplot(111)
    ax.set_aspect('equal', adjustable='datalim')
    ax.axis('off')
    ax.set_title(title, fontsize=10, fontweight='bold')
    _draw_envelope_on_ax(ax, solve_runs_rich, state, kind=kind)

    canvas = FigureCanvasQTAgg(fig)
    canvas.setMinimumHeight(340)
    vbox.addWidget(canvas)

    def _redraw(val: float) -> None:
        ax.cla()
        ax.set_aspect('equal', adjustable='datalim')
        ax.axis('off')
        ax.set_title(title, fontsize=10, fontweight='bold')
        _draw_envelope_on_ax(ax, solve_runs_rich, state, kind=kind, scale_mult=val)
        canvas.draw()

    spin.valueChanged.connect(_redraw)
    return w


# ── EnvelopeDialog ─────────────────────────────────────────────────────────────

class EnvelopeDialog(QDialog):
    """Show max/min envelope results across all load combinations."""

    def __init__(self, solve_runs_rich: list, state: ModelState,
                 parent=None) -> None:
        super().__init__(parent)
        n = len(solve_runs_rich)
        self.setWindowTitle(f"Envelope Results — {n} combination(s)")
        self.setMinimumWidth(860)
        self.setMinimumHeight(540)

        layout = QVBoxLayout(self)

        names = ", ".join(r['combo'].name for r in solve_runs_rich[:3])
        if n > 3:
            names += f" … (+{n - 3} more)"
        hdr = QLabel(
            f"<b>Envelope across {n} combination(s)</b>  ·  {names}<br>"
            "Tables show max/min at member <i>ends</i>. "
            "Diagram tabs show the full pointwise envelope along each member."
        )
        hdr.setWordWrap(True)
        layout.addWidget(hdr)

        tabs = QTabWidget()
        tabs.addTab(self._node_tab(solve_runs_rich, state),   "Node Displacements")
        tabs.addTab(self._member_tab(solve_runs_rich, state), "Member Forces")
        tabs.addTab(_make_plot_tab(solve_runs_rich, state, 'M'), "BMD Envelope")
        tabs.addTab(_make_plot_tab(solve_runs_rich, state, 'V'), "SFD Envelope")
        layout.addWidget(tabs)

        bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bbox.rejected.connect(self.accept)
        layout.addWidget(bbox)

    # ── node displacement table ────────────────────────────────────────────────

    def _node_tab(self, runs: list, state: ModelState) -> QTableWidget:
        tbl = QTableWidget(len(state.nodes), 5)
        tbl.setHorizontalHeaderLabels(
            ["Node", "Max δy (mm)", "Combo (max)", "Min δy (mm)", "Combo (min)"]
        )
        _style_table(tbl)

        env: dict[int, dict] = {
            nd.id: dict(max_dy=-1e18, max_c="", min_dy=1e18, min_c="")
            for nd in state.nodes
        }

        for run in runs:
            combo = run['combo'];  displacements = run['displacements']
            for nd in state.nodes:
                dy = displacements[nd.id * 3 + 1] * 1000
                e  = env[nd.id]
                if dy > e["max_dy"]:
                    e["max_dy"] = dy;  e["max_c"] = combo.name
                if dy < e["min_dy"]:
                    e["min_dy"] = dy;  e["min_c"] = combo.name

        for row, nd in enumerate(state.nodes):
            e = env[nd.id]
            tbl.setItem(row, 0, _cell(str(nd.id),            center=True))
            tbl.setItem(row, 1, _cell(f"{e['max_dy']:+.3f}", center=True))
            tbl.setItem(row, 2, _cell(e["max_c"]))
            tbl.setItem(row, 3, _cell(f"{e['min_dy']:+.3f}", center=True))
            tbl.setItem(row, 4, _cell(e["min_c"]))
        return tbl

    # ── member force table ─────────────────────────────────────────────────────

    def _member_tab(self, runs: list, state: ModelState) -> QTableWidget:
        cols = [
            "Member",
            "Max M+ (kNm)", "Combo",
            "Max M− (kNm)", "Combo",
            "Max |V| (kN)", "Combo",
            "Max N comp (kN)", "Combo",
            "Max N tens (kN)", "Combo",
        ]
        tbl = QTableWidget(len(state.members), len(cols))
        tbl.setHorizontalHeaderLabels(cols)
        _style_table(tbl)

        env: dict[int, dict] = {
            md.id: dict(
                max_M=-1e18, max_M_c="",
                min_M=1e18,  min_M_c="",
                max_absV=0.0, max_absV_c="",
                max_comp=0.0, max_comp_c="",
                max_tens=0.0, max_tens_c="",
            )
            for md in state.members
        }

        for run in runs:
            combo = run['combo'];  member_results = run['member_results']
            for r in member_results:
                e = env[r.element_id]
                for m_kn in (r.M_i / 1000, r.M_j / 1000):
                    if m_kn > e["max_M"]:  e["max_M"]  = m_kn; e["max_M_c"]  = combo.name
                    if m_kn < e["min_M"]:  e["min_M"]  = m_kn; e["min_M_c"]  = combo.name
                for v_kn in (abs(r.V_i / 1000), abs(r.V_j / 1000)):
                    if v_kn > e["max_absV"]: e["max_absV"] = v_kn; e["max_absV_c"] = combo.name
                for n_raw in (r.N_i, r.N_j):
                    comp = max(0.0,  n_raw / 1000)
                    tens = max(0.0, -n_raw / 1000)
                    if comp > e["max_comp"]: e["max_comp"] = comp; e["max_comp_c"] = combo.name
                    if tens > e["max_tens"]: e["max_tens"] = tens; e["max_tens_c"] = combo.name

        for row, md in enumerate(state.members):
            e = env[md.id]
            tbl.setItem(row, 0,  _cell(str(md.id),              center=True))
            tbl.setItem(row, 1,  _cell(f"{e['max_M']:+.3f}",   center=True))
            tbl.setItem(row, 2,  _cell(e["max_M_c"]))
            tbl.setItem(row, 3,  _cell(f"{e['min_M']:+.3f}",   center=True))
            tbl.setItem(row, 4,  _cell(e["min_M_c"]))
            tbl.setItem(row, 5,  _cell(f"{e['max_absV']:.3f}", center=True))
            tbl.setItem(row, 6,  _cell(e["max_absV_c"]))
            tbl.setItem(row, 7,  _cell(f"{e['max_comp']:.3f}", center=True))
            tbl.setItem(row, 8,  _cell(e["max_comp_c"]))
            tbl.setItem(row, 9,  _cell(f"{e['max_tens']:.3f}", center=True))
            tbl.setItem(row, 10, _cell(e["max_tens_c"]))
        return tbl
