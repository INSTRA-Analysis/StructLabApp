"""StructLab Python SDK — programmatic access to the StructLab solver.

Run analyses from Python scripts or Jupyter notebooks without opening the GUI.

Quick start
-----------
    import sdk as sl

    m = sl.Model()                # a plane frame in the XZ plane (Z up)
    n0 = m.add_node(0, 0, 0)      # (x, y, z): a plane frame's nodes have y = 0
    n1 = m.add_node(5, 0, 0)
    m.pin(n0)
    m.roller(n1)                  # free in X, held vertically
    m.add_member(n0, n1, E=210e9, A=6.64e-3, I=8.36e-5)
    m.add_udl(0, w=10e3)          # 10 kN/m downward

    result = m.solve()
    print(result.reactions(n0))   # [Fx, Fy, Fz, Mx, My, Mz]  (N, N·m); vertical is Fz
    print(result.max_moment(0))   # peak |M| along member 0
    fig = result.plot("BMD")      # matplotlib Figure

One axis convention everywhere, as in the app: X horizontal, Y depth, Z up.
``sl.Model()`` is a plane frame (2D analysis in its XZ plane: uy, θx, θz held at every
node); ``sl.Model(analysis="space")`` is a full 3D space frame.  The SDK no longer builds
2D (XY, Y up) models.
"""

from __future__ import annotations

import warnings as _warnings
from typing import Any

import numpy as np

from ui_qt.model_state import (
    ModelState,
    NodeData,
    MemberData,
    LoadCase,
    SupportType,
    ElementType,
    NodeLoad,
    MemberLoad,
    DistLoad,
    PartialDistLoad,
    PointLoadData,
)
from ui_qt.model_builder import build_model
from ui_qt.solve_actions import validate_model, solve_engine


# ── Model ─────────────────────────────────────────────────────────────────────

class Model:
    """Fluent builder for a StructLab structural model.

    Coordinates: X = horizontal, Y = depth, Z = up (vertical), as in the app.

    analysis : "plane" (default) — a plane frame in the XZ plane: put every node at y = 0
               (``add_node(x, 0, z)``); loads Fx, Fz, My act in its plane.
               "space" — a 3D space frame, all six DOFs per node.
    mode_3d  : older form: True means "space", False means "plane" (no longer 2D).
    """

    def __init__(self, analysis: str = "plane", *, mode_3d: bool | None = None) -> None:
        if mode_3d is not None:
            analysis = "space" if mode_3d else "plane"
        if analysis not in ("plane", "space"):
            raise ValueError(f"analysis must be 'plane' or 'space', got {analysis!r}")
        self._state = ModelState()                      # always 3D (Z up)
        self._state.analysis_type = "plane_xz" if analysis == "plane" else "space"
        # Rename the auto-created "Permanent (G)" case to 'default'
        self._state.load_cases[0].name = "default"
        self._lc_name_to_id: dict[str, int] = {"default": 0}

    @classmethod
    def from_state(cls, state: ModelState) -> "Model":
        """Wrap an existing ModelState (e.g. the live canvas state) as a Model.

        The state is used directly — not copied — so the model reflects the
        current canvas contents at the moment solve() is called.
        """
        obj = cls.__new__(cls)
        obj._state = state
        obj._lc_name_to_id = {lc.name: lc.id for lc in state.load_cases}
        return obj

    # ── Nodes ─────────────────────────────────────────────────────────────────

    def add_node(self, x: float, y: float, z: float = 0.0) -> int:
        """Add a node at (x, y, z) and return its id."""
        nd = self._state.add_node(x, y, z)
        return nd.id

    # ── Supports ──────────────────────────────────────────────────────────────

    def fixed(self, node_id: int) -> None:
        """Fully fixed support (all DOFs restrained)."""
        self._node(node_id).support_type = SupportType.FIXED

    def pin(self, node_id: int) -> None:
        """Pinned support (translations restrained, rotation free)."""
        self._node(node_id).support_type = SupportType.PIN

    def roller(self, node_id: int) -> None:
        """Roller free in X — held vertically (Z) and in Y."""
        self._node(node_id).support_type = SupportType.ROLLER

    def roller_y(self, node_id: int) -> None:
        """Roller free in Y — held in X and Z (space frames)."""
        self._node(node_id).support_type = SupportType.ROLLER_Y

    def roller_z(self, node_id: int) -> None:
        """Roller free vertically (Z) — held in X and Y (a wall roller in a plane frame)."""
        self._node(node_id).support_type = SupportType.ROLLER_Z

    # ── Members ───────────────────────────────────────────────────────────────

    def add_member(
        self,
        i: int,
        j: int,
        E: float,
        A: float,
        I: float,
        I_y: float | None = None,
        J: float = 0.0,
        n_sub: int = 4,
        element_type: str = "BEAM",
    ) -> int:
        """Add a member between nodes i and j and return its id.

        Parameters
        ----------
        i, j      : node ids
        E         : Young's modulus (Pa)
        A         : cross-section area (m²)
        I         : strong-axis moment of inertia I_z (m⁴)
        I_y       : weak-axis moment of inertia (m⁴); defaults to I if None
        J         : torsional constant (m⁴, 3D only)
        n_sub     : sub-elements for the internal mesh (default 4; results are exact per
                    element for every load type, so more only adds intermediate nodes)
        element_type : "BEAM" | "BAR" | "PIN_LEFT" | "PIN_RIGHT"
        """
        md = self._state.add_member(i, j)
        if md is None:
            raise ValueError(f"Cannot add member: node {i} or {j} not found")
        md.E = E
        md.A = A
        md.I = I
        md.I_y = I_y
        md.J = J
        md.n_sub = n_sub
        md.element_type = ElementType[element_type]
        return md.id

    # ── Loads ─────────────────────────────────────────────────────────────────

    def add_load_case(self, name: str, category: str = "Q") -> None:
        """Register a named load case (category: G/Q/W/S/E)."""
        lc = self._state.add_load_case(name, category)
        self._lc_name_to_id[name] = lc.id

    def add_point_load(
        self,
        node_id: int,
        Fx: float = 0.0,
        Fy: float = 0.0,
        Fz: float = 0.0,
        Mx: float = 0.0,
        My: float = 0.0,
        Mz: float = 0.0,
        lc: str | None = None,
    ) -> None:
        """Apply a nodal force/moment (N, N·m) in global axes."""
        load_case = self._load_case(lc)
        existing = load_case.get_node_load(node_id)
        load_case.set_node_load(
            node_id,
            NodeLoad(
                fx=existing.fx + Fx,
                fy=existing.fy + Fy,
                fz=existing.fz + Fz,
                moment=existing.moment + Mz,
                moment_x=existing.moment_x + Mx,
                moment_y=existing.moment_y + My,
            ),
        )

    def add_udl(
        self,
        member_id: int,
        w: float,
        direction: str = "w",
        lc: str | None = None,
    ) -> None:
        """Apply a uniform distributed load (N/m) along a member.

        direction: 'w' = local transverse (downward +), 'qz' = global -Z,
                   'qx' = global X, 'qy' = global Y.
        """
        load_case = self._load_case(lc)
        ml = load_case.get_member_load(member_id)
        ml.dist_loads.append(DistLoad(direction, w, w))
        load_case.set_member_load(member_id, ml)

    def add_varying_load(
        self,
        member_id: int,
        w_start: float,
        w_end: float,
        direction: str = "w",
        lc: str | None = None,
    ) -> None:
        """Apply a linearly varying distributed load (N/m) along a member."""
        load_case = self._load_case(lc)
        ml = load_case.get_member_load(member_id)
        ml.dist_loads.append(DistLoad(direction, w_start, w_end))
        load_case.set_member_load(member_id, ml)

    def add_partial_load(
        self,
        member_id: int,
        w: float,
        start: float,
        end: float,
        lc: str | None = None,
    ) -> None:
        """Apply a UDL over a fraction of member span.

        start, end: fractional positions (0.0 = node_i, 1.0 = node_j).
        """
        load_case = self._load_case(lc)
        ml = load_case.get_member_load(member_id)
        ml.partial_loads.append(PartialDistLoad(start, end, w, w))
        load_case.set_member_load(member_id, ml)

    def add_point_force_on_member(
        self,
        member_id: int,
        magnitude: float,
        position: float,
        lc: str | None = None,
    ) -> None:
        """Apply a concentrated transverse force on a member.

        position: fractional (0.0 = node_i, 1.0 = node_j).
        magnitude: N, downward positive.
        """
        load_case = self._load_case(lc)
        ml = load_case.get_member_load(member_id)
        ml.point_loads.append(PointLoadData("FORCE", position, magnitude))
        load_case.set_member_load(member_id, ml)

    # ── Solve ─────────────────────────────────────────────────────────────────

    def solve(self, lc: str | None = None) -> "SolveResult":
        """Run the FEM solver for the named load case and return results.

        With no `lc`, solves whichever case is currently active — for a
        fresh Model() that's its single "default" case; for Model.from_state()
        (e.g. the console's live `model`) that's whatever the app's own
        Case: dropdown has selected, matching what its Solve button would run.

        Raises RuntimeError if the model fails validation.
        """
        if lc is None:
            lc_id = self._state.active_case_id
            load_case = self._state.get_load_case(lc_id)
            if load_case is None:
                raise ValueError(f"No active load case (id {lc_id} not found).")
        else:
            lc_id = self._lc_name_to_id.get(lc)
            if lc_id is None:
                raise ValueError(f"Load case '{lc}' not found. "
                                 f"Available: {list(self._lc_name_to_id)}")
            load_case = self._state.get_load_case(lc_id)
        self._state.active_case_id = lc_id

        errors, warns = validate_model(self._state)
        if errors:
            raise RuntimeError("Model validation failed:\n" + "\n".join(f"  • {e}" for e in errors))
        for w in warns:
            _warnings.warn(w, stacklevel=2)

        model, member_el_map = build_model(self._state, load_case)
        cache = solve_engine(model, member_el_map, self._state)
        return SolveResult(cache, self._state, model)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _node(self, node_id: int) -> NodeData:
        nd = self._state.get_node(node_id)
        if nd is None:
            raise ValueError(f"Node {node_id} not found")
        return nd

    def _load_case(self, name: str | None) -> LoadCase:
        """Resolve a load case by name. None resolves to the model's
        currently active case (its single case for a fresh Model(); whatever
        the app's Case: dropdown has selected for Model.from_state()) rather
        than a literal "default" — creating a same-named case would be right
        for a fresh Model() but would silently fork off an orphan case that
        never gets solved for a canvas-wrapped one."""
        if name is None:
            lc = self._state.get_load_case(self._state.active_case_id)
            assert lc is not None
            return lc
        if name not in self._lc_name_to_id:
            self.add_load_case(name)
        lc = self._state.get_load_case(self._lc_name_to_id[name])
        assert lc is not None
        return lc


# ── SolveResult ───────────────────────────────────────────────────────────────

class SolveResult:
    """Results from a solved load case.

    All values in SI base units (N, N·m, m, rad) unless otherwise noted.
    """

    def __init__(self, cache: dict[str, Any], state: ModelState, core_model: Any) -> None:
        self._cache = cache
        self._state = state
        self._core = core_model
        self._dpn: int = core_model.dofs_per_node  # 3 (2D) or 6 (3D)
        # member UI id → position in state.members
        self._member_idx: dict[int, int] = {
            md.id: i for i, md in enumerate(state.members)
        }
        self._member_result_map = {r.element_id: r for r in cache["member_results"]}

    # ── Nodal results ─────────────────────────────────────────────────────────

    def reactions(self, node_id: int) -> np.ndarray:
        """Reaction force/moment vector at a support node: [Fx, Fy, Fz, Mx, My, Mz].

        Non-zero only at restrained DOFs.  In a plane frame the in-plane ones are
        Fx, Fz (vertical) and My.
        """
        start = node_id * self._dpn
        return self._cache["reactions"][start: start + self._dpn].copy()

    def displacement(self, node_id: int) -> np.ndarray:
        """Displacement/rotation vector at a node: [dx, dy, dz, θx, θy, θz].

        In a plane frame the in-plane ones are dx, dz (vertical) and θy; the rest are zero.
        """
        start = node_id * self._dpn
        return self._cache["displacements"][start: start + self._dpn].copy()

    # ── Member results ────────────────────────────────────────────────────────

    def member_forces(self, member_id: int) -> dict[str, float]:
        """End forces at member i- and j-ends in local coordinates.

        Plane frame keys (in-plane): N_i, V_i, M_i, N_j, V_j, M_j
        Space frame keys: N_i, V_y_i, V_z_i, T_i, M_y_i, M_z_i, N_j, V_y_j, V_z_j, T_j, M_y_j, M_z_j
        Sign: N+ = compression, V+ = up on left face, M+ = sagging.
        """
        er = self._member_result_map[member_id]
        if er.is_3d and self._state.analysis_type != "plane_xz":
            return dict(
                N_i=er.N_i, V_y_i=er.V_y_i, V_z_i=er.V_z_i,
                T_i=er.T_i, M_y_i=er.M_y_i, M_z_i=er.M_z_i,
                N_j=er.N_j, V_y_j=er.V_y_j, V_z_j=er.V_z_j,
                T_j=er.T_j, M_y_j=er.M_y_j, M_z_j=er.M_z_j,
            )
        return dict(
            N_i=er.N_i, V_i=er.V_i, M_i=er.M_i,
            N_j=er.N_j, V_j=er.V_j, M_j=er.M_j,
        )

    def max_moment(self, member_id: int) -> float:
        """Peak absolute bending moment along the member (N·m).

        Computed from the detailed sub-element diagram — accurate for distributed loads.
        """
        x, M, _ = self._member_diagram(member_id)
        return float(np.max(np.abs(M)))

    def max_shear(self, member_id: int) -> float:
        """Peak absolute shear force along the member (N)."""
        x, _, V = self._member_diagram(member_id)
        return float(np.max(np.abs(V)))

    # ── Plotting ──────────────────────────────────────────────────────────────

    def plot(
        self,
        kind: str = "BMD",
        member_id: int | None = None,
        n_points: int = 50,
        scale: float = 1.0,
    ):
        """Plot a force diagram and return a matplotlib Figure.

        Parameters
        ----------
        kind      : "BMD" | "SFD" | "AFD"
        member_id : plot only this member (None = all members)
        n_points  : sample points per sub-element
        scale     : vertical scale multiplier (useful for small/large values)
        """
        import matplotlib.pyplot as plt

        members = self._state.members
        if member_id is not None:
            members = [m for m in members if m.id == member_id]
        if not members:
            raise ValueError(f"Member {member_id} not found")

        labels = {"BMD": "M (N·m)", "SFD": "V (N)", "AFD": "N (N)"}
        fig, ax = plt.subplots(figsize=(10, 4))

        for md in members:
            x_arr, M_arr, V_arr = self._member_diagram(md.id, n_points)
            if kind == "BMD":
                values = -M_arr * scale   # flip: sagging below baseline (engineering convention)
            elif kind == "SFD":
                values = V_arr * scale
            elif kind == "AFD":
                er = self._member_result_map[md.id]
                values = np.full_like(x_arr, er.N_i * scale)
            else:
                raise ValueError(f"kind must be 'BMD', 'SFD', or 'AFD', got '{kind}'")

            ax.plot(x_arr, values, label=f"Member {md.id}")
            ax.fill_between(x_arr, values, alpha=0.15)
            ax.axhline(0, color="k", linewidth=0.5)

        ax.set_xlabel("Position along member (m)")
        ax.set_ylabel(labels.get(kind, kind))
        ax.set_title(kind)
        if len(members) > 1:
            ax.legend()
        fig.tight_layout()
        return fig

    # ── Internal ──────────────────────────────────────────────────────────────

    def _member_diagram(
        self, member_id: int, n_points: int = 50
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (x, M, V) arrays stitched across sub-elements of a member."""
        from solver.postprocessor import Postprocessor

        idx = self._member_idx[member_id]
        el_ids = set(self._cache["member_el_map"][idx])

        model = self._cache["model"]
        elements = [el for el in model.elements if el.id in el_ids]
        # Preserve order from member_el_map
        el_order = {eid: pos for pos, eid in enumerate(self._cache["member_el_map"][idx])}
        elements.sort(key=lambda el: el_order[el.id])

        pp = Postprocessor(elements, model.element_loads, self._cache["displacements"])
        sfd_bmd = pp.sfd_bmd(n_points=n_points)

        x_out: list[np.ndarray] = []
        M_out: list[np.ndarray] = []
        V_out: list[np.ndarray] = []
        offset = 0.0
        for seg in sfd_bmd:
            x_out.append(seg.x + offset)
            M_out.append(seg.M)
            V_out.append(seg.V)
            offset += seg.x[-1]

        return np.concatenate(x_out), np.concatenate(M_out), np.concatenate(V_out)


# ── Convenience re-exports ────────────────────────────────────────────────────

__all__ = ["Model", "SolveResult"]


# ── Quick self-test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("StructLab SDK — self-test: simply supported beam, UDL 10 kN/m, L = 6 m")

    m = Model()                       # plane frame in XZ
    n0 = m.add_node(0, 0, 0)
    n1 = m.add_node(6, 0, 0)
    m.pin(n0)
    m.roller(n1)

    E = 210e9        # Pa (steel)
    A = 6.64e-3      # m²  (IPE 300 approx)
    I = 8.356e-5     # m⁴  (IPE 300 approx)
    mid = m.add_member(n0, n1, E=E, A=A, I=I, n_sub=20)

    w = 10e3         # N/m
    m.add_udl(mid, w=w)

    result = m.solve()

    L = 6.0
    R_analytical = w * L / 2
    M_mid_analytical = w * L**2 / 8

    R0 = result.reactions(n0)
    R1 = result.reactions(n1)
    M_peak = result.max_moment(mid)

    print(f"  Reaction at n0 (Fz): {R0[2]/1e3:+.3f} kN  (expected {R_analytical/1e3:+.3f} kN)")
    print(f"  Reaction at n1 (Fz): {R1[2]/1e3:+.3f} kN  (expected {R_analytical/1e3:+.3f} kN)")
    print(f"  Peak moment:          {M_peak/1e3:.3f} kN·m  (expected {M_mid_analytical/1e3:.3f} kN·m)")

    tol = 0.001  # 0.1%
    assert abs(R0[2] - R_analytical) / R_analytical < tol, "Reaction check failed"
    assert abs(M_peak - M_mid_analytical) / M_mid_analytical < tol, "Moment check failed"
    print("  All checks passed.")

    fig = result.plot("BMD")
    fig.savefig("bmd_example.png", dpi=120)
    print("  BMD saved to bmd_example.png")
