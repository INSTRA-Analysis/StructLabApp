"""SDK example: single-bay portal frame with a horizontal wind load.

Geometry (X = horizontal, Z = up, 2D)
--------------------------------------
        n2--------(beam 6m)--------n3
        |                          |
     (col 4m)                  (col 4m)
        |                          |
        n0                         n1
       FIXED                      FIXED

Loads
-----
    Horizontal point load 20 kN at n2 (wind).
    Gravity UDL 15 kN/m on beam.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sdk as sl

m = sl.Model(mode_3d=False)

# Nodes  (X = horizontal, Y not used in 2D, Z = up → use x, y coords)
n0 = m.add_node(0, 0, 0)    # base left
n1 = m.add_node(6, 0, 0)    # base right
n2 = m.add_node(0, 4, 0)    # top  left
n3 = m.add_node(6, 4, 0)    # top  right

m.fixed(n0)
m.fixed(n1)

E = 210e9
A = 9.43e-3   # m²  (IPE 330 column)
I  = 1.17e-4  # m⁴  (IPE 330 column)

col_left  = m.add_member(n0, n2, E=E, A=A, I=I, n_sub=10)
col_right = m.add_member(n1, n3, E=E, A=A, I=I, n_sub=10)

E_b = 210e9
A_b = 11.4e-3   # m²  (IPE 400 beam)
I_b = 2.31e-4   # m⁴  (IPE 400 beam)

beam = m.add_member(n2, n3, E=E_b, A=A_b, I=I_b, n_sub=20)

# Wind (horizontal at top-left node)
m.add_point_load(n2, Fx=20e3, lc="default")
# Gravity UDL on beam
m.add_udl(beam, w=15e3, lc="default")

result = m.solve()

print("Portal frame results")
print("=" * 40)
for nid, label in [(n0, "n0 (base-left)"), (n1, "n1 (base-right)")]:
    r = result.reactions(nid)
    print(f"  {label}: Fx={r[0]/1e3:+.2f} kN  Fy={r[1]/1e3:+.2f} kN  Mz={r[2]/1e3:+.2f} kN·m")

for mid, label in [(col_left, "col-left"), (col_right, "col-right"), (beam, "beam")]:
    print(f"  Max |M| {label}: {result.max_moment(mid)/1e3:.2f} kN·m")

# Horizontal equilibrium check
r0 = result.reactions(n0)
r1 = result.reactions(n1)
net_Fx = r0[0] + r1[0] + 20e3    # applied 20 kN + both reactions should sum to 0
print(f"\n  Horizontal equilibrium residual: {net_Fx:.6f} N  (should be ~0)")

fig = result.plot("BMD")
fig.savefig("portal_frame_bmd.png", dpi=120)
print("  BMD saved to portal_frame_bmd.png")
