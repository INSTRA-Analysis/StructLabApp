"""CSV import for StructLab models.

Reads a single *sectioned* CSV file into a :class:`ModelState`. The format mirrors
the four data blocks used by typical truss spreadsheets (nodes / members / supports /
forces), but each block is a labelled section in ONE file rather than side-by-side
columns:

    # comment lines and blank lines are ignored
    #NODES
    id,x,y,z
    1,-4.0,-4.0,0.0
    ...
    #MEMBERS
    id,node_i,node_j,etype,group,E,A,fy,density
    1,8,4,bar,Leg,2e11,0.005,2.75e8,7950
    ...
    #SUPPORTS
    node,rx,ry,rz
    1,1,1,1
    ...
    #FORCES
    node,Fx,Fy,Fz
    49,0,0,-5000

Conventions (the importer does **no** axis rotation — author the file in StructLab's
native frame):
  * Units are SI throughout: metres, newtons, pascals, kg/m³.
  * Z is the vertical (up) axis. Downward loads are ``Fz < 0``.
  * The first non-comment row after a ``#SECTION`` header names the columns, so column
    *order* is tolerant — lookup is by header name.

Member columns:
  * ``etype`` — analysis element type, consumed by the solver:
    ``bar`` (pin-pin, axial only — the truss member), ``beam`` (full 6×6),
    ``pin_i`` / ``pin_j`` (single-end release). Case-insensitive; defaults to ``bar``.
  * ``group`` — a free descriptive label (e.g. Leg / Diagonal / Horizontal) used only
    for display and reporting. Stored on :attr:`MemberData.group`.

CSV node/member ids are arbitrary user labels; they are remapped to StructLab's own
auto-incrementing ids internally, so the file may number things however it likes.
"""

from __future__ import annotations

import csv
from pathlib import Path

from ui_qt.model_state import (
    ElementType,
    ModelState,
    NodeLoad,
    SupportType,
)

# ── mapping tables ────────────────────────────────────────────────────────────

_ETYPE_MAP: dict[str, ElementType] = {
    "bar": ElementType.BAR,
    "truss": ElementType.BAR,
    "beam": ElementType.BEAM,
    "frame": ElementType.BEAM,
    "pin_i": ElementType.PIN_LEFT,
    "pin_left": ElementType.PIN_LEFT,
    "pin_j": ElementType.PIN_RIGHT,
    "pin_right": ElementType.PIN_RIGHT,
}

# Translational restraint triple (rx, ry, rz) → support type. Rotations are immaterial
# for all-BAR (truss) nodes, so a fully restrained node maps cleanly to FIXED.
_SUPPORT_MAP: dict[tuple[int, int, int], SupportType] = {
    (1, 1, 1): SupportType.FIXED,
    (1, 1, 0): SupportType.ROLLER_Z,   # free in Z, restrained in X,Y
}

_SECTION_KEYS = {"NODES", "MEMBERS", "SUPPORTS", "FORCES"}


# ── helpers ───────────────────────────────────────────────────────────────────

def _to_float(value: str, default: float = 0.0) -> float:
    """Parse a CSV cell to float, tolerating blanks and stray whitespace."""
    value = (value or "").strip()
    if not value:
        return default
    return float(value)


def _to_int(value: str) -> int:
    return int(float((value or "").strip()))


def _split_sections(path: str | Path) -> dict[str, list[list[str]]]:
    """Split a sectioned CSV into ``{SECTION_NAME: [row, ...]}``.

    Blank lines and ``#`` comment lines are skipped, except ``#SECTION`` markers
    that switch the active section. Rows are returned verbatim (the first data row
    of each section is its header).
    """
    sections: dict[str, list[list[str]]] = {}
    current: str | None = None
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for raw_row in csv.reader(fh):
            if not raw_row:
                continue
            first = raw_row[0].strip()
            if first.startswith("#"):
                key = first.lstrip("#").strip().upper()
                if key in _SECTION_KEYS:
                    current = key
                    sections.setdefault(current, [])
                # any other '#...' line is a comment — ignore
                continue
            if current is None:
                continue  # data before the first section header — ignore
            sections[current].append(raw_row)
    return sections


def _rows_as_dicts(rows: list[list[str]]) -> list[dict[str, str]]:
    """Use the first row as a header and zip the rest into per-row dicts."""
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]
    out: list[dict[str, str]] = []
    for row in rows[1:]:
        if not any(cell.strip() for cell in row):
            continue  # skip fully blank data rows
        out.append({header[i]: row[i] for i in range(min(len(header), len(row)))})
    return out


# ── main entry point ──────────────────────────────────────────────────────────

def parse_structlab_csv(path: str | Path) -> tuple[ModelState, list[str]]:
    """Parse a sectioned StructLab CSV into a :class:`ModelState`.

    Returns the built state plus a list of human-readable warnings (the import is
    best-effort: a bad member row is skipped with a warning rather than aborting).
    """
    warnings: list[str] = []
    sections = _split_sections(path)

    state = ModelState()
    state.mode_3d = True
    csv_to_internal: dict[int, int] = {}  # CSV node id → NodeData.id

    # ── NODES ──────────────────────────────────────────────────────────────────
    for row in _rows_as_dicts(sections.get("NODES", [])):
        try:
            csv_id = _to_int(row["id"])
            x = _to_float(row.get("x", ""))
            y = _to_float(row.get("y", ""))
            z = _to_float(row.get("z", ""))
        except (KeyError, ValueError) as exc:
            warnings.append(f"NODES: skipped malformed row {row} ({exc})")
            continue
        if csv_id in csv_to_internal:
            warnings.append(f"NODES: duplicate node id {csv_id} — keeping the first")
            continue
        node = state.add_node(x, y, z)
        csv_to_internal[csv_id] = node.id

    # ── MEMBERS ────────────────────────────────────────────────────────────────
    for row in _rows_as_dicts(sections.get("MEMBERS", [])):
        try:
            ni_csv = _to_int(row["node_i"])
            nj_csv = _to_int(row["node_j"])
        except (KeyError, ValueError) as exc:
            warnings.append(f"MEMBERS: skipped malformed row {row} ({exc})")
            continue
        if ni_csv not in csv_to_internal or nj_csv not in csv_to_internal:
            warnings.append(
                f"MEMBERS: member {row.get('id', '?')} references missing node "
                f"({ni_csv}→{nj_csv}) — skipped"
            )
            continue

        member = state.add_member(csv_to_internal[ni_csv], csv_to_internal[nj_csv])
        if member is None:  # defensive — should not happen given the check above
            warnings.append(f"MEMBERS: could not create member {row.get('id', '?')}")
            continue

        etype_str = (row.get("etype", "") or "bar").strip().lower()
        etype = _ETYPE_MAP.get(etype_str)
        if etype is None:
            warnings.append(
                f"MEMBERS: member {row.get('id', '?')} unknown etype "
                f"'{etype_str}' — defaulting to bar"
            )
            etype = ElementType.BAR
        member.element_type = etype
        member.group = (row.get("group", "") or "").strip()
        # header keys are lower-cased by _rows_as_dicts, so look up lower-case names
        member.E = _to_float(row.get("e", ""), member.E)
        member.A = _to_float(row.get("a", ""), member.A)
        member.fy = _to_float(row.get("fy", ""), member.fy)
        member.density = _to_float(row.get("density", ""), member.density)
        # Optional bending properties for beam/frame members (ignored by bars,
        # which are axial-only). Omit these columns for pure trusses.
        member.I = _to_float(row.get("i", ""), member.I)
        member.J = _to_float(row.get("j", ""), member.J)
        iy = (row.get("iy", "") or "").strip()
        if iy:                       # explicit weak-axis I; else defaults to I
            member.I_y = _to_float(iy, member.I)

    # ── SUPPORTS ───────────────────────────────────────────────────────────────
    for row in _rows_as_dicts(sections.get("SUPPORTS", [])):
        try:
            node_csv = _to_int(row["node"])
            rx, ry, rz = _to_int(row["rx"]), _to_int(row["ry"]), _to_int(row["rz"])
        except (KeyError, ValueError) as exc:
            warnings.append(f"SUPPORTS: skipped malformed row {row} ({exc})")
            continue
        if node_csv not in csv_to_internal:
            warnings.append(f"SUPPORTS: node {node_csv} not found — skipped")
            continue
        triple = (rx, ry, rz)
        sup = _SUPPORT_MAP.get(triple)
        if sup is None:
            sup = SupportType.FIXED
            warnings.append(
                f"SUPPORTS: node {node_csv} restraint {triple} not directly "
                f"representable — using FIXED"
            )
        node = state.get_node(csv_to_internal[node_csv])
        if node is not None:
            node.support_type = sup

    # ── FORCES ─────────────────────────────────────────────────────────────────
    case = state.active_case
    for row in _rows_as_dicts(sections.get("FORCES", [])):
        try:
            node_csv = _to_int(row["node"])
        except (KeyError, ValueError) as exc:
            warnings.append(f"FORCES: skipped malformed row {row} ({exc})")
            continue
        if node_csv not in csv_to_internal:
            warnings.append(f"FORCES: node {node_csv} not found — skipped")
            continue
        fx = _to_float(row.get("fx", ""))
        fy = _to_float(row.get("fy", ""))
        fz = _to_float(row.get("fz", ""))
        if fx or fy or fz:
            case.set_node_load(csv_to_internal[node_csv], NodeLoad(fx=fx, fy=fy, fz=fz))

    return state, warnings
