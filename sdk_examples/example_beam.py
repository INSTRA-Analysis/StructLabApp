"""SDK example: two-span continuous beam with a UDL and a point load.

Geometry
--------
    n0-----(span 1, 6 m)-----n1-----(span 2, 4 m)-----n2
    PIN                      PIN                       ROLLER

Loads
-----
    LC1 (dead):  UDL  20 kN/m on span 1
    LC2 (live):  point load 50 kN at midspan of span 2
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sdk as sl

# ── Build model ───────────────────────────────────────────────────────────────

m = sl.Model(mode_3d=False)

n0 = m.add_node(0, 0)
n1 = m.add_node(6, 0)
n2 = m.add_node(10, 0)

m.pin(n0)
m.pin(n1)
m.roller(n2)

E = 210e9        # Pa  (steel)
A = 11.4e-3      # m²  (IPE 400)
I = 2.31e-4      # m⁴  (IPE 400)

span1 = m.add_member(n0, n1, E=E, A=A, I=I, n_sub=20)
span2 = m.add_member(n1, n2, E=E, A=A, I=I, n_sub=20)

# Load case 1 — UDL on span 1
m.add_load_case("dead", category="G")
m.add_udl(span1, w=20e3, lc="dead")

# Load case 2 — midspan point load on span 2
m.add_load_case("live", category="Q")
m.add_point_force_on_member(span2, magnitude=50e3, position=0.5, lc="live")

# ── Solve and report ──────────────────────────────────────────────────────────

for lc_name in ("dead", "live"):
    result = m.solve(lc=lc_name)
    print(f"\n-- {lc_name.upper()} LOAD CASE --------------")

    for nid, label in [(n0, "n0"), (n1, "n1"), (n2, "n2")]:
        r = result.reactions(nid)
        if abs(r).max() > 1:
            print(f"  Reaction {label}: Fy = {r[1]/1e3:+.2f} kN,  Mz = {r[2]/1e3:+.2f} kN·m")

    for mid, label in [(span1, "span 1"), (span2, "span 2")]:
        print(f"  Max |M| {label}: {result.max_moment(mid)/1e3:.2f} kN·m")
        print(f"  Max |V| {label}: {result.max_shear(mid)/1e3:.2f} kN")

# ── Plot ──────────────────────────────────────────────────────────────────────

import matplotlib.pyplot as plt

fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=False)

for ax, lc_name in zip(axes, ("dead", "live")):
    result = m.solve(lc=lc_name)
    for mid in (span1, span2):
        x, M, V = result._member_diagram(mid)
        # offset x for second span
        if mid == span2:
            x = x + 6.0
        ax.plot(x, -M / 1e3, label=f"Member {mid}")
        ax.fill_between(x, -M / 1e3, alpha=0.15)
    ax.axhline(0, color="k", linewidth=0.5)
    ax.set_title(f"BMD — {lc_name}")
    ax.set_ylabel("M (kN·m)")
    ax.legend()

axes[-1].set_xlabel("Position (m)")
fig.tight_layout()
plt.savefig("continuous_beam_bmd.png", dpi=120)
print("\nBMD saved to continuous_beam_bmd.png")
