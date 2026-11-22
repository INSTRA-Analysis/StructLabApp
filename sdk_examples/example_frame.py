"""SDK example: single-bay portal frame, built and solved IN the StructLab app.

Run it from the app's console (Tools > Python Console) with any project open.
Copy the code, then paste it (Ctrl+V, or %paste for long blocks). It replaces
whatever is on the canvas, builds the frame there as a plane frame, and runs the
app's own Solve, so the BMD / SFD / AFD / Deformed diagrams and the results tables
appear on the real structure, using the toolbar overlay buttons.

Geometry (plane frame in the XZ plane: X = horizontal, Z = vertical)
--------------------------------------------------------------------
        n2--------(beam 6m)--------n3
        |                          |
     (col 4m)                  (col 4m)
        |                          |
        n0                         n1
       FIXED                      FIXED

Loads (added to the currently active load case)
-----------------------------------------------
    Horizontal point load 20 kN at n2 (wind).
    Gravity UDL 15 kN/m on the beam.

Console names used: model (live canvas model), state, refresh(), solve().

NOTE: there are deliberately no blank lines inside indented blocks below, so
the code also pastes cleanly into a terminal (a blank line would end the block).
"""

if "state" not in globals():
    raise RuntimeError("Run this inside StructLab: Tools > Python Console, then paste it.")

# ── Clear the canvas (members first, so their loads go too) ──────────────────

for member in list(state.members):
    state.remove_member(member.id)
for node in list(state.nodes):
    state.remove_node(node.id)

# A plane frame: 3D model, Z up, analysed in its XZ plane (uy, θx, θz held at every node)
state.analysis_mode = "3D"
state.analysis_type = "plane_xz"

# ── Build the frame on the canvas ─────────────────────────────────────────────

# Nodes (x, y, z) — the frame lies in the plane y = 0, z is the vertical axis
n0 = model.add_node(0, 0, 0)    # base left
n1 = model.add_node(6, 0, 0)    # base right
n2 = model.add_node(0, 0, 4)    # top  left
n3 = model.add_node(6, 0, 4)    # top  right

model.fixed(n0)
model.fixed(n1)

E = 210e9
A = 9.43e-3   # m²  (IPE 330 column)
I = 1.17e-4   # m⁴  (IPE 330 column)

col_left = model.add_member(n0, n2, E=E, A=A, I=I, n_sub=10)
col_right = model.add_member(n1, n3, E=E, A=A, I=I, n_sub=10)

A_b = 11.4e-3   # m²  (IPE 400 beam)
I_b = 2.31e-4   # m⁴  (IPE 400 beam)

beam = model.add_member(n2, n3, E=E, A=A_b, I=I_b, n_sub=20)

# Wind (horizontal at top-left node) and gravity UDL on the beam ('w' acts downward)
model.add_point_load(n2, Fx=20e3)
model.add_udl(beam, w=15e3)

# ── Show it and solve it in the app ───────────────────────────────────────────

refresh()   # redraw the canvas with the new frame (shown from the front)
solve()     # same as pressing Solve: results tables + BMD/SFD/AFD/Deformed overlays
print(f"Solved load case '{state.active_case.name}' — use the overlay buttons to switch diagrams.")
