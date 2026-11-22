"""Groups panel: one row per member group with visibility, quantities and profile.

The pure helpers (``group_rows``, ``apply_section``) hold the logic and are tested
without a display; ``GroupsPanel`` is the thin Qt shell around them. A row shows a
colour swatch (the same colour as "Colour by Group"), a visibility checkbox, the member
count, total length, mass and the profile name; the buttons select the group's members
and assign a library profile to all of them at once.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui_qt.model_state import MemberData, ModelState

UNGROUPED = "(no group)"
_COLUMNS = ["", "Group", "Members", "Length (m)", "Mass (kg)", "Profile"]


@dataclass(frozen=True)
class GroupRow:
    name: str                   # "" for members without a group
    member_ids: tuple[int, ...]
    length: float               # total length [m]
    mass: float                 # total mass [kg] (members with density and area only)
    profile: str                # library name, "mixed (n)", or "A = … cm²"

    @property
    def label(self) -> str:
        return self.name or UNGROUPED


def member_length(state: ModelState, m: MemberData) -> float:
    ni, nj = state.get_node(m.node_i), state.get_node(m.node_j)
    if ni is None or nj is None:
        return 0.0
    return math.dist((ni.x, ni.y, ni.z), (nj.x, nj.y, nj.z))


def _profile_label(members: list[MemberData]) -> str:
    from ui_qt.panels import _build_section_lookup      # lazy: panels imports the canvas
    lookup = _build_section_lookup()
    names = {lookup.get((round(m.A, 8), round(m.I, 12))) or f"A = {m.A * 1e4:.2f} cm²"
             for m in members}
    if len(names) == 1:
        return next(iter(names))
    return f"mixed ({len(names)})"


def group_rows(state: ModelState) -> list[GroupRow]:
    """Groups in first-seen order, ungrouped members (if any) last."""
    buckets: dict[str, list[MemberData]] = {}
    for m in state.members:
        buckets.setdefault((m.group or "").strip(), []).append(m)
    ordered = [g for g in buckets if g] + ([""] if "" in buckets else [])
    rows = []
    for g in ordered:
        ms = buckets[g]
        length = sum(member_length(state, m) for m in ms)
        mass = sum(member_length(state, m) * m.A * m.density
                   for m in ms if m.A > 0 and m.density > 0)
        rows.append(GroupRow(g, tuple(m.id for m in ms), length, mass, _profile_label(ms)))
    return rows


def apply_section(members: list[MemberData], result: tuple, extra: dict | None) -> None:
    """Write a section-picker result onto every member.

    ``result`` is ``SectionPickerDialog.get_result()``:
    (E, A, I, W_pl, W_el, b, h, density, fy, material_type); ``extra`` its get_extra()
    (angles: I_y = minor principal moment, J). Optional values the picker leaves at 0
    keep what the member already had — except I_y and J: a profile without them (I-/H-sections)
    clears them, so a member never keeps another section's weak axis (flagged in space frames).
    """
    E, A, I, W_pl, W_el, b, h, density, fy, _material = result
    for m in members:
        m.E, m.A, m.I, m.density, m.fy = E, A, I, density, fy
        if W_pl > 0:
            m.W_pl = W_pl
        if W_el > 0:
            m.W_el = W_el
        if b > 0:
            m.b_sec = b
        if h > 0:
            m.h_sec = h
        if extra:
            m.I_y, m.J = extra["I_y"], extra["J"]
        else:
            m.I_y, m.J = None, 0.0


class GroupsPanel(QWidget):
    """Table of member groups bound to a StructCanvas."""

    changed = pyqtSignal()          # a profile was assigned (model data changed)

    def __init__(self, scene) -> None:
        super().__init__()
        self._scene = scene
        self._rows: list[GroupRow] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self._summary = QLabel("")
        self._summary.setStyleSheet("color: #888888;")
        lay.addWidget(self._summary)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setStretchLastSection(True)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.itemDoubleClicked.connect(lambda _it: self._select_current())
        lay.addWidget(self._table)

        buttons = QHBoxLayout()
        self._btn_select = QPushButton("Select")
        self._btn_select.setToolTip("Select every member of the chosen group (double-click a row too)")
        self._btn_select.clicked.connect(self._select_current)
        self._btn_profile = QPushButton("Profile…")
        self._btn_profile.setToolTip("Assign a library section to every member of the chosen group")
        self._btn_profile.clicked.connect(self._assign_profile)
        self._btn_show = QPushButton("Show all")
        self._btn_show.clicked.connect(self._show_all)
        for b in (self._btn_select, self._btn_profile, self._btn_show):
            buttons.addWidget(b)
        lay.addLayout(buttons)

    # ── content ───────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        from ui_qt.canvas_items import group_colour
        state = self._scene.model_state
        self._rows = group_rows(state)
        keep = self._current_name()
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            check.setCheckState(Qt.CheckState.Unchecked if row.name in self._scene._hidden_groups
                                else Qt.CheckState.Checked)
            self._table.setItem(r, 0, check)
            name = QTableWidgetItem(row.label)
            if row.name:
                name.setForeground(QBrush(group_colour(row.name)))
            else:
                name.setForeground(QBrush(QColor("#888888")))
            self._table.setItem(r, 1, name)
            for c, text in ((2, str(len(row.member_ids))), (3, f"{row.length:,.1f}"),
                            (4, f"{row.mass:,.0f}" if row.mass else "—"), (5, row.profile)):
                item = QTableWidgetItem(text)
                if c in (2, 3, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(r, c, item)
        self._table.blockSignals(False)
        for r, row in enumerate(self._rows):
            if row.name == keep:
                self._table.selectRow(r)
        total_len = sum(r.length for r in self._rows)
        total_mass = sum(r.mass for r in self._rows)
        self._summary.setText(f"{len(self._rows)} groups   {total_len:,.1f} m   {total_mass / 1000:,.2f} t")

    def _current_name(self) -> str | None:
        r = self._table.currentRow()
        return self._rows[r].name if 0 <= r < len(self._rows) else None

    def _current_row(self) -> GroupRow | None:
        r = self._table.currentRow()
        return self._rows[r] if 0 <= r < len(self._rows) else None

    # ── actions ───────────────────────────────────────────────────────────────

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0 or not 0 <= item.row() < len(self._rows):
            return
        self._scene.set_group_hidden(self._rows[item.row()].name,
                                     item.checkState() != Qt.CheckState.Checked)

    def _show_all(self) -> None:
        self._scene.show_all_groups()
        self.refresh()

    def _select_current(self) -> None:
        row = self._current_row()
        if row:
            self._scene.select_members(row.member_ids)

    def _assign_profile(self) -> None:
        row = self._current_row()
        if not row:
            return
        from ui_qt.section_picker import SectionPickerDialog
        members = [m for m in self._scene.model_state.members if m.id in set(row.member_ids)]
        first = members[0]
        dlg = SectionPickerDialog(current_E=first.E, current_A=first.A, current_I=first.I, parent=self)
        if not (dlg.exec() and dlg.get_result()):
            return
        self._scene.save_snapshot()
        apply_section(members, dlg.get_result(), dlg.get_extra())
        self._scene.model_changed.emit()
        self.changed.emit()
        self.refresh()
