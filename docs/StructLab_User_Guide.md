# StructLab — User Guide
**Version:** V0.2 BETA  
**Audience:** Peer reviewers and colleagues evaluating StructLab for 2D structural analysis  
**Last updated:** May 2026

---

## Contents

1. [What StructLab Does](#1-what-structlab-does)
2. [Launching the App](#2-launching-the-app)
3. [Interface Overview](#3-interface-overview)
4. [Canvas Navigation](#4-canvas-navigation)
5. [Building a Model](#5-building-a-model)
6. [Element Types](#6-element-types)
7. [Support Types](#7-support-types)
8. [Applying Loads](#8-applying-loads)
9. [Load Cases](#9-load-cases)
10. [Member Properties](#10-member-properties)
11. [Solving](#11-solving)
12. [EN 1990 Load Combinations](#12-en-1990-load-combinations)
13. [Viewing Results](#13-viewing-results)
14. [Diagram Overlays](#14-diagram-overlays)
15. [Preset Models](#15-preset-models)
16. [Save and Load Files](#16-save-and-load-files)
17. [Worked Example: Simply Supported Beam](#17-worked-example-simply-supported-beam)
18. [Sign Conventions](#18-sign-conventions)
19. [Keyboard Shortcuts](#19-keyboard-shortcuts)
20. [Known Limitations](#20-known-limitations)

---

## 1. What StructLab Does

StructLab solves **2D linear-elastic static** structural models using the Direct Stiffness Method (DSM). It handles:

| Structure type | Description |
|---|---|
| **Beams** | Horizontal members with bending and shear; supports UDL and point loads |
| **Frames** | Full rigid-jointed 2D frames (columns + beams, any geometry) |
| **Trusses** | Pin-jointed bar networks carrying axial force only |
| **Mixed** | Any combination — e.g. a beam with a bar prop, or a braced frame |

**What it outputs:**
- Nodal displacements (dx, dy in mm; rotation θ in mrad)
- Support reactions (kN and kN·m)
- Member end forces: axial N, shear V, moment M at both ends
- Bending moment diagram (BMD), shear force diagram (SFD), axial force diagram (AFD)
- Deformed shape (scalable)
- EN 1990 load combination results and envelope (max/min across all combinations)

**What it does NOT do:**
- 3D structures
- Dynamic / seismic analysis
- Buckling or stability analysis
- Plastic / nonlinear material behaviour
- Moving loads or influence lines (solver engine supports them; UI does not yet expose them)

---

## 2. Launching the App

### Option A — Standalone executable (Windows)
* Double-click StructLab.exe in the distribution folder.
* No Python installation is required.
* Please note: Administrator privileges are required to approve the initial launch of this newly published application.


### Option B — From source (development)
```
for developers: cd C:\StructLabApp
python ui_qt/main.py
```
Requires Python 3.12 and all packages in `requirements.txt` installed.

---

## 3. Interface Overview

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  Toolbar 1:  New | Open | Save | MODELING: Select/Node/Member                 │
│              Type combo | Case combo | +/− | SW | Solve | Combinations…       │
├───────────────────────────────────────────────────────────────────────────────┤
│  Toolbar 2:  Clear Results | BMD SFD AFD Def Labels                           │
│              Force colours | Diag × | Def × | Combo view selector             │
├──────────────────────────────┬──────────────────────────────┬─────────────────┤
│  Properties panel            │  Canvas                      │  Results panel  │
│  (left dock)                 │  (grid-snapped 2D workspace) │  (right dock)   │
│                              │                              │                 │
│  Click a node or member      │  Build and view your model   │  Displacements /│
│  to inspect and edit it.     │  here. Overlays drawn after  │  Reactions /    │
│  Click Apply to confirm.     │  solving.                    │  Members tabs   │
└──────────────────────────────┴──────────────────────────────┴─────────────────┘
│  Status bar: current mode, solve summary, error messages                      │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Toolbar 1 — Modeling and Solving

| Control | Description |
|---|---|
| **New / Open / Save** | File operations (see Section 16) |
| **Select / Add Node / Add Member** | Toggle canvas mode; shortcuts `S`, `N`, `M` |
| **Type** combo | Member type for the next draw action (BEAM, BAR, PIN_LEFT, PIN_RIGHT) |
| **Case** combo | Active load case — loads shown on canvas belong to this case |
| **+** / **−** buttons | Add or remove a load case |
| **SW** button | Toggle self-weight inclusion in the current load case |
| **Solve** | Solve the active load case; shortcut `F5` |
| **Combinations…** | Open the EN 1990 load combination manager |

### Toolbar 2 — Visualization

| Control | Description |
|---|---|
| **Clear Results** | Remove all overlays and reset the Results panel |
| **BMD / SFD / AFD / Def / Labels** | Toggle diagram overlays on/off |
| **Force colours** | Colour members by axial force (red = compression, blue = tension) |
| **Diag ×** | Diagram amplitude multiplier (default 1.0) |
| **Def ×** | Deformation scale multiplier (default 1.0) |
| **Combo view** | Select which combination to display when multiple have been solved |

### Panels

**Properties (left dock):** Shows editable fields for the selected node or member. Click **Apply** after making changes. When nothing is selected, shows a model summary.

**Results (right dock):** Three sub-tabs appear after a successful solve — **Displacements**, **Reactions**, **Members**. Clicking a row in any tab highlights the corresponding item on the canvas, and vice versa.

---

## 4. Canvas Navigation

The canvas is a scrollable, zoomable 2D workspace. All navigation uses only the mouse — no mode switching needed.

### Zoom

| Action | Result |
|---|---|
| **Scroll wheel up** | Zoom in (×1.15 per step), centred on the cursor position |
| **Scroll wheel down** | Zoom out (÷1.15 per step), centred on the cursor position |
| Press **`F`** | **Zoom to fit** — fits all model elements in view with one grid unit of padding |

> **Tip:** Because zoom is always centred on the cursor, position your cursor over the region of interest before scrolling. This avoids the model drifting off-screen when zooming in on a specific joint.

### Pan (Move the view)

| Action | Result |
|---|---|
| **Hold middle mouse button and drag** | Pan the canvas in any direction |

Release the middle button to stop panning. The cursor changes to a closed-hand icon while panning.

> **Note:** Left-click drag is reserved for rubber-band selection (in Select mode) and for drawing members (in Add Member mode). Middle-button drag is always available regardless of the current canvas mode.

### Zoom to Fit

Press **`F`** at any time to automatically scale and centre the view so that all nodes and members are visible with one metre of padding on each side.

Zoom to fit also runs automatically when:
- A preset model is loaded from the Presets menu
- A `.slab` file is opened via File → Open

### Moving Nodes

Node dragging is a canvas *editing* operation, not a navigation operation. To drag a node:

1. Press **`S`** to enter Select mode.
2. Click the node to select it.
3. **Click and drag** the node to a new position.

Nodes snap to the 0.25 m grid during dragging. All connected members move with the node. An undo snapshot is saved automatically before each drag.

### Rubber-band Selection

In Select mode, **click and drag on empty canvas space** to draw a selection rectangle. All nodes and members that fall inside the rectangle are selected. Use `Ctrl+A` to select everything.

---

## 5. Building a Model

The workflow is always: **place nodes → connect members → assign supports and loads → solve**.

### Step 1 — Add nodes

1. Click **Add Node** in the toolbar (or press `N`).
2. Click on the canvas. A node snaps to the nearest 0.25 m grid point.
3. Repeat for all nodes you need.

> **Tip:** You do not need to pre-plan every node. Intermediate nodes along a member can be added later and connected with additional members.

### Step 2 — Connect members

1. Click **Add Member** in the toolbar (or press `M`).
2. Click the **start node**, then click the **end node**. A line appears connecting them.
3. A ghost preview line follows your cursor while drawing.

> **Tip:** Choose the member type (BEAM / BAR / PIN_LEFT / PIN_RIGHT) in the **Type** combo *before* clicking, or change it afterwards via the Properties panel.

### Step 3 — Assign supports and loads

1. Press `S` (or click **Select**) to enter select mode.
2. Click a node to select it; its properties appear in the left panel.
3. Set **Support type** and/or **Nodal loads** (Fx, Fy, M), then click **Apply**.

### Step 4 — Assign member properties

1. In Select mode, click a member.
2. Edit **E**, **A**, **I**, distributed load (**w start** / **w end**), and any point loads in the Properties panel, then click **Apply**.
3. Steel section presets (IPE/HEB series) can be selected from the list; this fills E, A, I automatically.

### Step 5 — Solve

Click the blue **Solve** button or press `F5`.

### Editing and deleting

- **Move a node:** Select it, then drag it (moves all attached members).
- **Delete:** Select a node or member and press `Delete`.
- **Undo/Redo:** `Ctrl+Z` / `Ctrl+Y`. Note: undo clears results; re-solve after undoing.
- **Select multiple:** Click and drag a rubber-band box in Select mode. Use `Ctrl+A` to select all.

---

## 6. Element Types

Set via the **Type** dropdown in Toolbar 1 before drawing, or in the Properties panel after selecting a member.

| Type | Behaviour | Typical use |
|---|---|---|
| **BEAM** | Full rigid connection at both ends; carries N, V, M | Beams, frame columns, any rigid-jointed member |
| **BAR** | Pinned at both ends; axial force only (N), no moment | Truss members, diagonal bracing |
| **PIN_LEFT** | Pin release at the *start* node (node i); moment = 0 at that end | Gerber beam left hinge; pinned column base |
| **PIN_RIGHT** | Pin release at the *end* node (node j); moment = 0 at that end | Gerber beam right hinge |

> **Note on BAR elements:** At a node connected *only* to BAR members, the rotational DOF is automatically excluded from the solver (no rotational stiffness there). This is handled internally; you do not need to do anything special.

---

## 7. Support Types

Set via the **Support type** dropdown in the Properties panel for each node.

| Type | Restrained DOFs | Symbol on canvas |
|---|---|---|
| **FREE** | None — unsupported node | No symbol |
| **PIN** | dx, dy | Triangle (point up) |
| **ROLLER** | dy only (free to slide horizontally) | Triangle on wheels |
| **ROLLER_Y** | dx only (free to slide vertically) | Triangle on wheels, pointing left |
| **FIXED** | dx, dy, θ | Rectangle (wall) |
| **SPRING** | Elastic restraint; stiffness set via kx, ky, kθ fields | Triangle with spring |

> **Rule:** Every model must have at least one **PIN** or **FIXED** support. A structure with only ROLLERs cannot resist horizontal forces and will be flagged as an error before solving.

---

## 8. Applying Loads

Loads in StructLab belong to a **load case** (see Section 9). The canvas always shows the loads of the active case. Switch the active case in the **Case** combo before editing loads.

### Nodal loads
Select a node → Properties panel:

| Field | Description | Units |
|---|---|---|
| **Fx** | Horizontal force at the node | kN (positive = rightward) |
| **Fy** | Vertical force at the node | kN (positive = upward, so **enter negative** for gravity) |
| **M** | Applied moment at the node | kN·m (positive = counter-clockwise) |

> **Common mistake:** Gravity loads are *negative* Fy. Enter `-10` for a 10 kN downward point load.

### Member distributed load (UDL / UVL)
Select a member → Properties panel, **Distributed load** group:

| Field | Description | Units |
|---|---|---|
| **w start** | Load intensity at node i (start of member) | kN/m (positive = **downward**) |
| **w end** | Load intensity at node j (end of member) | kN/m (positive = **downward**) |

- Set both equal → **uniform distributed load (UDL)**.
- Set them unequal → **linearly varying load (UVL / trapezoidal)**. For example, w start = 20, w end = 0 gives a triangular load that is full at node i and zero at node j.
- Set both to zero to remove the distributed load.

> **Note:** Distributed load sign convention is **reversed** from nodal Fy: positive values are downward (gravity-positive). Enter `20` for a 20 kN/m downward UDL.

> **Sign note for element direction:** The start/end intensities follow the element's draw direction (node i → node j). If a member was drawn right-to-left, node i is on the right. This does not affect the solver — if the diagram looks inverted simply swap w start and w end, or flip the sign.

### Point loads and moments on members
Select a member → Properties panel, **Point loads** table. Each row defines one concentrated load applied at a fractional position along the member.

| Column | Description |
|---|---|
| **Type** | `Force ↓` — transverse point force; `Moment ↺` — concentrated moment |
| **Pos (0–1)** | Position along the member as a fraction of its length (0 = node i, 1 = node j) |
| **Value** | Magnitude in kN (force) or kN·m (moment); positive = downward / counter-clockwise |

Use the buttons below the table to manage rows:

| Button | Action |
|---|---|
| **+ Force** | Add a new transverse point force row (default position 0.5, value 0) |
| **+ Moment** | Add a new concentrated moment row (default position 0.5, value 0) |
| **Remove** | Delete the selected row |

Click **Apply** to commit all distributed and point load changes together.

> **Tip:** Multiple point loads can coexist with a UDL/UVL on the same member. All are superposed by the solver correctly via fixed-end force vectors.

---

## 9. Load Cases

StructLab supports **multiple named load cases** in one model. Each load case holds its own set of nodal and member loads. This lets you define permanent loads (dead), variable loads (live), wind, snow, etc. separately, then combine them using EN 1990 combinations (Section 12).

### Managing load cases

| Control | Action |
|---|---|
| **Case** combo (Toolbar 1) | Switch the active load case; the canvas updates to show that case's loads |
| **+ button** | Open a dialog to add a new named load case and assign its EN 1990 category |
| **− button** | Remove the active load case (disabled when only one case exists) |
| **SW button** | Toggle self-weight on the current load case (see below) |

### Load case categories (EN 1990)

When adding a load case, assign a category so StructLab can apply the correct EN 1990 partial factors and combination rules automatically:

| Category | EN 1990 symbol | Description |
|---|---|---|
| **G** | Permanent | Self-weight, superimposed dead load |
| **Q** | Variable | Imposed live load |
| **W** | Wind | Wind action |
| **S** | Snow | Snow load |
| **E** | Seismic | Seismic action |

### Self-weight (SW)

Click **SW** in Toolbar 1 to include member self-weight in the active load case. StructLab computes self-weight from each member's cross-sectional area, member density, and length, and applies it as equivalent nodal forces. Only one load case can carry self-weight at a time.

> **Prerequisite:** Member density must be set in the Member Properties panel. Steel defaults to 7850 kg/m³.

---

## 10. Member Properties

Select a member → Properties panel:

| Field | Description | Default |
|---|---|---|
| **E** | Young's modulus | 210 GPa (steel) |
| **A** | Cross-sectional area | 0.03 m² |
| **I** | Second moment of area | 300×10⁻⁶ m⁴ |
| **w start / w end** | Distributed load intensity at each end (UDL if equal, UVL if unequal) | 0 kN/m |
| **Density** | Material density for self-weight | 7850 kg/m³ (steel) |
| **Mesh n** | Sub-elements for diagram resolution | 10 |
| **Profile** | Steel section preset (auto-fills E, A, I) | — |

### Steel section presets

Selecting a profile from the dropdown automatically fills E, A, I with EN 10365 / EN 10210 values:

| Profile | A (cm²) | I (cm⁴) | Typical use |
|---|---|---|---|
| IPE 300 | 53.8 | 8 356 | Light beams, purlins |
| IPE 360 | 72.7 | 16 270 | Mid-span floor beams |
| IPE 400 | 84.5 | 23 130 | Floor beams |
| IPE 450 | 98.8 | 33 740 | Heavy floor beams |
| IPE 500 | 116.0 | 48 200 | Long-span beams |
| HEB 220 | 91.0 | 8 091 | Light columns |
| HEB 260 | 118.4 | 14 920 | Mid-height columns |
| HEB 300 | 149.1 | 25 170 | Standard columns |
| HEB 340 | 170.9 | 36 660 | Heavy columns |
| SHS 150×150×8 | 45.4 | 1 532 | Bracing diagonals |
| SHS 200×200×10 | 76.0 | 4 585 | Truss chords |

All values use E = 210 GPa (EN 1993-1-1, S355 structural steel).

---

## 11. Solving

### Running the solver
Click the blue **Solve** button or press `F5`.

This solves the **active load case** only. To solve all EN 1990 combinations at once, use **Combinations…** (Section 12).

The solver runs through:
1. Pre-solve validation (see below)
2. Global stiffness matrix assembly
3. Linear system solve (LU factorisation)
4. Reaction recovery
5. Internal force postprocessing (N, V, M at each sub-element station)
6. Diagram overlay generation

The status bar shows a summary: `Solved | Max deflection: X.XX mm (node N) | Max moment: Y.YY kN·m (member M)`.

### Pre-solve validation

The app checks your model before attempting to solve and reports:

**Errors (block solving):**
- Floating node — a node with no members attached
- No supports at all
- Only ROLLER supports (no PIN or FIXED)
- Zero-length member (two nodes at the same point)

**Warnings (you can proceed):**
- No loads applied — results will all be zero

### Singular matrix errors

If the solver itself detects a singular stiffness matrix, a dialog explains the likely cause:
- Missing support
- Mechanism (the structure can move as a rigid body)
- Truss with insufficient bracing

---

## 12. EN 1990 Load Combinations

StructLab implements **EN 1990 Table A1.2(B)** load combinations. Click **Combinations…** in Toolbar 1 to open the combination manager.

### Workflow

1. Define your load cases (G, Q, W, S…) as described in Section 9.
2. Open **Combinations…**.
3. Click **Auto-generate** to create all EN 1990 ULS and SLS combinations automatically.
4. Review the generated table — edit factors or add manual combinations if needed.
5. Click **Solve All** to solve every combination and compute the envelope.

### Auto-generated combinations

| Combination type | Partial factors | Produced |
|---|---|---|
| **ULS fundamental** | γG = 1.35 (G), γQ = 1.50 (leading Q), ψ₀·γQ (companion Q) | One per variable load case |
| **SLS characteristic** | 1.0 (G), 1.0 (leading Q), ψ₀ (companion Q) | One per variable load case |
| **SLS quasi-permanent** | 1.0 (G), ψ₂ (all Q cases) | One total |

Default ψ factors from EN 1990 Annex A1 (buildings): ψ₀ = 0.7 (Q), 0.6 (W), 0.5 (S); ψ₂ = 0.3 (Q), 0.0 (W), 0.2 (S).

Previously auto-generated combinations are replaced when you re-run Auto-generate. Manually-added combinations are preserved.

### Viewing combination results

After **Solve All**, the **Combo view** selector in Toolbar 2 becomes active:

| Option | What is displayed |
|---|---|
| **Active case** | Single-case result (from the **Solve** button) |
| **Envelope (max/min)** | Filled envelope showing the maximum and minimum across all combinations at every point |
| **All combos superposed** | All combination diagrams drawn together in distinct colours |
| *Individual combination name* | Single combination diagram |

The envelope is also available as a tabular results view in the Envelope Results dialog (opened from within the Combinations dialog).

### Pattern loading (EN 1992-1-1 §5.1.3)

When Q loads act on two or more connected spans, StructLab detects this and warns that pattern loading may be required. In pattern loading, Q is applied to alternating spans (or adjacent spans) to find the worst-case mid-span sagging moment in each span. StructLab generates the critical pattern arrangements automatically and includes them in the Solve All run.

---

## 13. Viewing Results

Results populate automatically after a successful solve. The Results panel (right dock) has three tabs:

### Displacements tab

| Column | Units | Description |
|---|---|---|
| Node | — | Node ID |
| dx | mm | Horizontal displacement |
| dy | mm | Vertical displacement (negative = downward) |
| θ | mrad | Rotation (positive = counter-clockwise) |

### Reactions tab

| Column | Units | Description |
|---|---|---|
| Node | — | Node ID (supported nodes only) |
| Rx | kN | Horizontal reaction |
| Ry | kN | Vertical reaction (positive = upward) |
| M | kN·m | Moment reaction (FIXED supports only) |

### Members tab

End forces at node i (start) and node j (end) of each member:

| Column | Units | Description |
|---|---|---|
| Member | — | Member ID |
| Ni / Nj | kN | Axial force at each end (positive = tension) |
| Vi / Vj | kN | Shear force at each end |
| Mi / Mj | kN·m | Bending moment at each end (positive = sagging) |

### Canvas–table synchronisation

Clicking a row in any results tab selects the corresponding node or member on the canvas and centres the Properties panel on it. Conversely, clicking a node or member on the canvas highlights its row in the results table.

---

## 14. Diagram Overlays

After solving, Toolbar 2 becomes active. Toggle overlays on/off with the buttons:

| Button | Overlay | Default |
|---|---|---|
| **BMD** | Bending moment diagram (filled, sagging below baseline) | ON |
| **SFD** | Shear force diagram (filled blue) | OFF |
| **AFD** | Axial force diagram (red = compression, blue = tension) | OFF |
| **Def** | Deformed shape (red dashed overlay) | ON |
| **Labels** | Peak value labels on diagrams | OFF |
| **Force colours** | Members coloured by axial state (red/blue) | OFF |

### Scale controls

| Spinner | Effect |
|---|---|
| **Diag ×** | Multiplies diagram amplitude (default 1.0). Increase if diagrams appear tiny; decrease if they overlap geometry. |
| **Def ×** | Multiplies deformation scale (default 1.0). Increase to make small deflections visible. |

Both spinners take effect immediately without re-solving.

### BMD sign convention (important for peer review)

The BMD is drawn using **standard structural engineering convention**:
- **Sagging** (positive moment, tension on bottom fibre) → plotted **below** the member baseline
- **Hogging** (negative moment, tension on top fibre) → plotted **above** the member baseline

The numerical values in the Members results table use the same sign: **positive M = sagging**.

---

## 15. Preset Models

Access via the **Presets** menu. Presets load a fully configured model ready to solve immediately. Zoom to fit runs automatically on load.

### EN Steel showcase presets

Higher-complexity models with real European steel profiles and EN-based loads:

| Preset | Description |
|---|---|
| **Setback Office Frame** | 6-story setback frame, HEB columns, IPE beams, gravity + wind load cases |
| **Braced Industrial Frame** | 2-story 4-bay with SHS K-bracing, heavy floor loads + wind load cases |
| **Pratt Truss Bridge** | 12 m span, 6-panel Pratt truss, SHS chords + web, 40 kN panel loads |
| **Continuous Beam (3-span)** | 3×4 m = 12 m, IPE 500, w=35 kN/m, FIXED–ROLLER–ROLLER–PIN |

### Frame Wizard

**Presets → Frame Wizard…** opens a dialog to generate a regular multi-story frame:

| Parameter | Range | Description |
|---|---|---|
| Number of bays | 1–20 | Bays in plan direction |
| Number of stories | 1–30 | Stories above ground |
| Bay width | 1–50 m | Uniform bay width |
| Story height | 1–20 m | Uniform story height |

All columns get PIN supports at base. Beam loads must be assigned manually after generation.

---

## 16. Save and Load Files

StructLab saves models in `.slab` format (a JSON text file).

| Action | How |
|---|---|
| **Save** | File → Save… (or `Ctrl+S`) — choose a filename, `.slab` is added automatically |
| **Open** | File → Open… (or `Ctrl+O`) — browse to a `.slab` file |
| **New** | File → New (or `Ctrl+N`) — clears the current model (no confirmation prompt) |

The `.slab` file stores: node positions, support types, nodal loads, member connectivity, element types, E/A/I/UDL for each member, spring stiffness values, all load cases (names, categories, loads), and load combinations. Results are **not** saved — re-solve after opening.

---

## 17. Worked Example: Simply Supported Beam

This walks through a complete session from scratch. Expected result: midspan deflection = 1.587 mm.

**Setup:**
- Span L = 4 m
- E = 210 GPa, I = 1×10⁻⁴ m⁴, A = 0.01 m²
- Point load P = 10 kN downward at midspan
- Analytical solution: δ = PL³/48EI = (10000 × 4³)/(48 × 210e9 × 1e-4) = **1.587 mm**

**Steps:**

1. Launch StructLab.
2. Press `N` (Add Node mode). Click to place three nodes at approximately:
   - Node 0: x=0, y=0
   - Node 1: x=2, y=0 (midspan)
   - Node 2: x=4, y=0
3. Press `M` (Add Member mode). Click Node 0 → Node 1, then Node 1 → Node 2.
4. Press `S` (Select mode). Click **Node 0**:
   - Set Support type = **PIN** → Apply
5. Click **Node 2**:
   - Set Support type = **ROLLER** → Apply
6. Click **Node 1**:
   - Set Fy = **-10** (kN, downward) → Apply
7. Click **Member 0** (left half):
   - Verify E = 210e9, A = 0.01, I = 1e-4 → Apply
   - Repeat for Member 1 (right half) — defaults should already match.
8. Click **Solve** (or press `F5`).
9. In the **Displacements** tab: Node 1 dy should read approximately **-1.587 mm**.
10. Toggle **BMD** on in Toolbar 2 — a parabola peaking downward at midspan should appear.

**What to check as a reviewer:**
- dy at node 1 matches PL³/48EI = 1.587 mm (within 0.1%)
- Ry at nodes 0 and 2 = 5.0 kN each (P/2 by symmetry)
- Mi and Mj at the two member ends show: 0 at supports, 10 kN·m at midspan (= PL/4)
- BMD shows sagging (plotted below the beam line)

---

## 18. Sign Conventions

This section matters most for peer review — these choices differ from some other tools.

### Nodal loads

| Load | Positive direction |
|---|---|
| Fx | Rightward (+x) |
| Fy | Upward (+y) — gravity loads are **negative** |
| M | Counter-clockwise |

### UDL on members

| Load | Positive direction |
|---|---|
| UDL w | **Downward** (gravity-positive) — opposite to Fy convention |

### Internal forces (Members results table)

| Force | Positive = |
|---|---|
| N (axial) | **Tension** (member is being pulled apart) |
| V (shear) | Conventional beam shear (upward on left face) |
| M (moment) | **Sagging** (tension on bottom fibre, concave upward) |

### BMD display

The plot flips the moment sign so that sagging moments appear **below** the member (standard UK/EU engineering drawing convention). The number shown as `Mi` or `Mj` in the table is the true signed moment — just the plot is mirrored.

### Reactions

Reactions are in global coordinates: Ry positive = upward push from support onto structure.

---

## 19. Keyboard Shortcuts

| Key | Action |
|---|---|
| `S` | Enter Select mode |
| `N` | Enter Add Node mode |
| `M` | Enter Add Member mode |
| `F5` | Solve (active load case) |
| `F` | Zoom to fit (fit all model elements in view) |
| `Delete` | Delete selected node(s) / member(s) |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+A` | Select all |
| `Ctrl+N` | New model |
| `Ctrl+O` | Open model file |
| `Ctrl+S` | Save model file |

**Mouse controls (canvas navigation — always available):**

| Action | Effect |
|---|---|
| Scroll wheel up/down | Zoom in/out, centred on the cursor |
| Middle-button drag | Pan the canvas |
| `F` key | Zoom to fit all model elements |
| Left-click drag (Select mode, empty space) | Rubber-band multi-select |
| Left-click drag on a node (Select mode) | Move the node (grid-snapped) |

---

## 20. Known Limitations

| Limitation | Notes |
|---|---|
| **2D only** | All structure and loads must lie in the x–y plane |
| **Linear elastic only** | No material plasticity, no geometric nonlinearity |
| **Static loads only** | No dynamic, seismic, or time-history analysis |
| **No moving loads in UI** | The solver engine supports influence lines but the UI does not yet expose them |
| **No buckling check** | Axial forces are computed correctly; Euler buckling is not checked |
| **No temperature or prestress loads** | Only mechanical loads (forces, moments, UDL, UVL) are supported; temperature gradients and prestress are not |
| **No result export** | Results are visible in the UI but cannot be exported to CSV/PDF from within the app yet |
| **Undo clears results** | After undo/redo the model must be re-solved |

---

*StructLab is developed using the Direct Stiffness Method. All core validation cases pass against analytical solutions (see `tests/` folder). For questions or bug reports contact the developer.*
