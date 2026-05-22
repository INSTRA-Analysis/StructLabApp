# Member Properties — User Guide

This guide explains every field in the **Member Properties** panel. Open the panel by selecting a member in the canvas and viewing the left dock.

---

## Element Type

Controls how the member behaves structurally.

| Type | Behaviour |
|---|---|
| **Beam** | Full frame element — carries axial force, shear, and bending moment. Default for most structures. |
| **Bar** | Axial-only (truss member) — carries tension and compression only, no moment. Use for all truss diagonals and chords. |
| **Pin-Left** | Moment release at the start node (node i). The member can rotate freely at that end — like a pinned connection on the left side. |
| **Pin-Right** | Moment release at the end node (node j). Free rotation at the right side. |

---

## Section Properties

These define the cross-sectional geometry and material stiffness of the member.

### E — Young's Modulus (GPa)

The material stiffness. Controls how much the member deforms under load.

| Material | Typical E |
|---|---|
| Steel | 210 GPa |
| Concrete | 29–35 GPa (Ecm) |
| Timber GL24h / GL28h | 11.5–12.6 GPa |
| Aluminium | 70 GPa |

### A — Cross-sectional Area (m²)

The total area of the cross-section. Governs:
- **Axial stiffness**: EA/L
- **Axial capacity**: N_pl = A × fy (used in the utilization check)
- **Self-weight**: ρ × A × g × L per unit length

### I_z — Strong-axis Moment of Inertia (×10⁻⁶ m⁴)

The second moment of area about the major bending axis. Governs flexural stiffness EI/L³ and bending resistance. For a standard horizontal beam this is the vertical (in-plane) bending axis.

### I_y — Weak-axis Moment of Inertia (×10⁻⁶ m⁴) *(3D only)*

Second moment of area about the minor axis. Used when the member carries out-of-plane bending or when a full 3D space frame analysis is required. Defaults to I_z if left at the same value.

### J — Torsional Constant (×10⁻⁶ m⁴) *(3D only)*

Controls torsional stiffness GJ/L. For open sections (IPE, HEA) J is very small; for closed hollow sections (CHS, RHS) it is much larger and torsion is efficiently resisted.

### β angle (rad) *(3D only)*

Section roll angle — rotates the cross-section about its own longitudinal axis. Use when the member's strong axis is not aligned with the gravity direction, for example:

- A diagonal purlin oriented at an angle to the rafter
- A column with its web rotated out of the plane of the frame
- Any member where the local y-axis needs to point in a specific direction

### fy — Yield Strength (MPa)

The design yield strength of the material, used for the EC3 utilization check. Standard steel grades:

| Grade | fy |
|---|---|
| S235 | 235 MPa |
| S275 | 275 MPa *(default)* |
| S355 | 355 MPa |
| S460 | 460 MPa |

If you are using concrete or timber, set fy to the relevant design strength (fcd or fmd) for a meaningful utilization ratio, or leave it at the default and interpret the result qualitatively.

### W_pl — Plastic Section Modulus (cm³)

The plastic section modulus about the strong axis. Together with fy it defines the plastic moment resistance:

> **M_pl = W_pl × fy**

Used for the EC3 utilization ratio displayed when the **Util %** overlay is active:

> **η = N_Ed / (A · fy) + M_Ed / (W_pl · fy)**

- Leave at **0** to compute utilization based on axial force only.
- Automatically populated when you pick a section from the library.
- For custom sections: a solid rectangle b×h gives W_pl = b·h²/4; a solid circle of diameter d gives W_pl = d³/6.

### Pick from library…

Opens the section picker dialog. Selecting any standard Euronorm profile (IPE, HEA, HEB, CHS, RHS) automatically sets **E**, **A**, **I_z**, and **W_pl** in one step. Custom tab pages let you enter rectangular, T-beam, circular, or hollow rectangular geometry and compute A and I analytically.

---

## Material / Density

### Material preset

Shortcut dropdown to set common material densities:

| Preset | Density |
|---|---|
| Steel | 7850 kg/m³ |
| Concrete | 2500 kg/m³ |
| Timber | 500 kg/m³ |
| Custom | Edit the density field directly |

Switching preset updates the density field automatically.

### Density (kg/m³)

Used to compute self-weight when the **Self-weight** load case is enabled (toolbar toggle). The self-weight load per unit length is ρ × A × g.

Set to **0** to exclude this member from self-weight calculations — useful for non-structural members, secondary elements, or when you prefer to model self-weight as an explicit distributed load.

---

## Distributed Loads *(active load case)*

These are loads applied continuously along the member length. They are stored in the **currently active load case** shown at the top of the toolbar. Switch the active load case before editing to assign loads to a different case.

### ↓ w start / w end (kN/m) — Transverse (local ⊥)

Distributed load acting perpendicular to the member's local axis. **Positive = downward** relative to the member's own orientation (not necessarily vertical).

- Set start = end for a **uniform distributed load (UDL)**
- Set different values for a **trapezoidal (linearly varying) load**

This is the most common load type for gravity-loaded beams.

### → qx start / qx end (kN/m) — Lateral (global X)

Distributed load in the global X direction. Positive = pointing in the +X direction. Typical use: horizontal wind pressure on a vertical or inclined member.

### ⊙ qz start / qz end (kN/m) — Lateral (global Z) *(3D only)*

Distributed load in the global Z (vertical) direction. Positive = pointing in the +Z direction. Used in 3D models where global-axis loads are more convenient than local-axis loads.

---

## Point Loads on Member *(active load case)*

Concentrated forces or moments applied at a specific fractional position along the member span.

| Column | Meaning |
|---|---|
| **Type** | *Force ↓* — transverse point force (kN); *Moment ↺* — in-plane concentrated moment (kN·m) |
| **Pos (0–1)** | Position as a fraction of the member length: 0 = start node (i), 0.5 = midspan, 1 = end node (j) |
| **Value** | Magnitude — positive values follow the same sign convention as the transverse load (downward positive for forces, CCW positive for moments) |

Use **+ Force** / **+ Moment** to add a row. Use **Remove** to delete the selected row. Multiple point loads can be combined on the same member.

---

## Analysis Mesh

### Sub-elements

The number of finite elements the member is subdivided into during analysis. This does not change the structural model — it only affects the resolution of:

- The **deformed shape** drawing
- The **SFD / BMD / AFD diagram** curves (more sub-elements = smoother curves with better peak detection)

| Sub-elements | Typical use |
|---|---|
| 1–4 | Very fast; only useful for simple trusses or when only global displacements matter |
| **10** | Default — adequate for most beams and frames |
| 20–50 | Recommended for long members under heavy distributed loads where accurate peak moment location is important |
| > 50 | Rarely needed; increases solve time noticeably |

---

## Apply

Commits all changes in the panel to the model. **Changes are not applied until you press Apply** — you can adjust multiple fields and apply them together. After applying, press **Solve** (toolbar) to update diagrams and results.
