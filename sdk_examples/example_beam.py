"""SDK example: two-span continuous beam with a UDL and a point load.

Runs two ways:
  * as a script:                 python sdk_examples/example_beam.py
  * pasted into the StructLab console (copy the code, then paste, or use %paste)

Geometry
--------
    n0-----(span 1, 6 m)-----n1-----(span 2, 4 m)-----n2
    PIN                      PIN                       ROLLER

Loads
-----
    LC1 (dead):  UDL  20 kN/m on span 1
    LC2 (live):  point load 50 kN at midspan of span 2

NOTE: there are deliberately no blank lines inside indented blocks below, so
the code also pastes cleanly into a terminal (a blank line would end the block).
"""

import os
import sys

# Script mode only: make the repo root importable. In the console __file__ does
# not exist and `sdk` is already available, so this is skipped.
if "__file__" in globals():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import sdk as sl
import matplotlib.pyplot as plt

# ── Build model ───────────────────────────────────────────────────────────────

m = sl.Model()                   # a plane frame in the XZ plane (Z up)

x0, x1, x2 = 0.0, 6.0, 10.0      # node positions along the beam (m)
n0 = m.add_node(x0, 0, 0)        # (x, y, z): the beam lies along X at y = z = 0
n1 = m.add_node(x1, 0, 0)
n2 = m.add_node(x2, 0, 0)

m.pin(n0)
m.pin(n1)
m.roller(n2)

E = 210e9        # Pa  (steel)
A = 11.4e-3      # m²  (IPE 400)
I = 2.31e-4      # m⁴  (IPE 400)

span1 = m.add_member(n0, n1, E=E, A=A, I=I, n_sub=20)
span2 = m.add_member(n1, n2, E=E, A=A, I=I, n_sub=20)

w_dead = 20e3    # N/m  UDL on span 1
P_live = 50e3    # N    point load at midspan of span 2

# Load case 1 — UDL on span 1
m.add_load_case("dead", category="G")
m.add_udl(span1, w=w_dead, lc="dead")

# Load case 2 — midspan point load on span 2
m.add_load_case("live", category="Q")
m.add_point_force_on_member(span2, magnitude=P_live, position=0.5, lc="live")

# ── Solve and report ──────────────────────────────────────────────────────────

results = {lc_name: m.solve(lc=lc_name) for lc_name in ("dead", "live")}

for lc_name, result in results.items():
    print(f"\n-- {lc_name.upper()} LOAD CASE --------------")
    for nid, label in [(n0, "n0"), (n1, "n1"), (n2, "n2")]:
        r = result.reactions(nid)
        print(f"  Reaction {label}: Fz = {r[2]/1e3:+.2f} kN,  My = {r[4]/1e3:+.2f} kN·m")
    for mid, label in [(span1, "span 1"), (span2, "span 2")]:
        print(f"  Max |M| {label}: {result.max_moment(mid)/1e3:.2f} kN·m,  Max |V| {label}: {result.max_shear(mid)/1e3:.2f} kN")

# ── Plot ──────────────────────────────────────────────────────────────────────

fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
for ax, (lc_name, result) in zip(axes[:2], results.items()):
    for mid, x_start in ((span1, x0), (span2, x1)):
        x, M, V = result._member_diagram(mid)
        ax.plot(x + x_start, -M / 1e3, label=f"Member {mid}")
        ax.fill_between(x + x_start, -M / 1e3, alpha=0.15)
    ax.axhline(0, color="k", linewidth=0.5)
    ax.set_title(f"BMD — {lc_name}")
    ax.set_ylabel("M (kN·m)")
    ax.legend()

# Third plot — the beam, its supports and both load cases
ax = axes[2]
ax.plot([x0, x2], [0, 0], color="k", linewidth=5, solid_capstyle="butt")
ax.plot([x0, x1, x2], [-0.1] * 3, "^", color="k", markerfacecolor="none", markersize=14)
ax.plot([x2], [-0.3], "o", color="k", markerfacecolor="none", markersize=9)
# Dead load: UDL on span 1
ax.plot([x0, x1], [0.5, 0.5], color="tab:blue")
for xa in np.linspace(x0, x1, 13):
    ax.annotate("", xy=(xa, 0.05), xytext=(xa, 0.5), arrowprops=dict(arrowstyle="-|>", color="tab:blue"))
ax.text((x0 + x1) / 2, 0.6, f"Dead: UDL {w_dead / 1e3:.0f} kN/m", ha="center", color="tab:blue")
# Live load: point load at midspan of span 2
x_live = x1 + 0.5 * (x2 - x1)
ax.annotate("", xy=(x_live, 0.05), xytext=(x_live, 1.0), arrowprops=dict(arrowstyle="-|>", color="tab:red", lw=2))
ax.text(x_live, 1.08, f"Live: {P_live / 1e3:.0f} kN", ha="center", color="tab:red")
# Node labels and span lengths
for nid, xn in ((n0, x0), (n1, x1), (n2, x2)):
    ax.text(xn, -0.65, f"n{nid}", ha="center")
for xa, xb in ((x0, x1), (x1, x2)):
    ax.text((xa + xb) / 2, -0.5, f"{xb - xa:g} m", ha="center", color="gray")
ax.set_ylim(-0.8, 1.35)
ax.set_yticks([])
ax.set_title("Beam, supports and loads")
axes[-1].set_xlabel("Position (m)")
fig.tight_layout()
plt.show()
