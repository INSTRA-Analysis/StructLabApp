# StructLab CSV import

Import a structure from a single **sectioned CSV** file via **File ▸ Import ▸ From CSV…**.

## Files here
- `truss_template.csv` — a minimal, commented skeleton to copy and edit.
- `transmission_tower_3d.csv` — a worked example: an 85-node / 318-member pin-jointed
  steel transmission tower (converted from the "3D Truss Toolbox" example data).

## Format

One file, four labelled sections. Blank lines and `#` comment lines are ignored. Each
`#SECTION` header is followed by a **column-name row**, so column order doesn't matter —
columns are matched by name.

```
#NODES
id,x,y,z
#MEMBERS
id,node_i,node_j,etype,group,E,A,fy,density
#SUPPORTS
node,rx,ry,rz
#FORCES
node,Fx,Fy,Fz
```

## Conventions

- **Units are SI**: metres, newtons, pascals, kg/m³.
- **Z is the vertical (up) axis.** Author coordinates in StructLab's native frame — the
  importer does **no** axis rotation. A downward load is `Fz < 0`.
- **Ids are arbitrary labels.** Node/member ids are remapped internally, so number them
  however you like; members and supports just have to reference existing node ids.

### Members
- `etype` — analysis element type (case-insensitive):
  - `bar` — pin-pin, axial only (the truss member). Only `E` and `A` matter.
  - `beam` — full bending element.
  - `pin_i` / `pin_j` — single-end moment release.
- `group` — a free descriptive label (e.g. `Leg`, `Diagonal`, `Horizontal`) used only for
  display and reporting; it has no effect on the analysis.
- `density` is stored on the member but only contributes load when a self-weight load case
  is enabled. To convert a self-weight given as γ in N/m³, divide by g ≈ 9.81 to get kg/m³.

### Supports
`rx, ry, rz` are translational restraints (`1` = fixed, `0` = free) in X, Y, Z.
`1,1,1` is a fully pinned/fixed node (rotations are irrelevant for an all-`bar` truss).
`1,1,0` maps to a Z-roller. Other partial combinations import as fully fixed with a warning.

### Forces
Nodal point loads in newtons along the global axes. `Fz < 0` is downward.

Any rows the importer can't use (bad node reference, unknown `etype`, malformed numbers)
are skipped and reported in a summary dialog — the rest of the model still loads.
