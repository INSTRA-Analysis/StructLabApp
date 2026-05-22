# StructLab — User Guide

**2D Structural Analysis · Direct Stiffness Method · v1.0**

---

## Overview

StructLab solves beams, frames, trusses, and mixed structures using the Direct Stiffness Method. All structure types share a single unified engine — element behaviour is controlled by section properties and pin-release flags, not separate solvers.

---

## Interface

```
┌─────────────────────────────────────────────────────────────┐
│  Menu bar      File · Presets                               │
│  Toolbar       Mode · Member type · Solve · Clear Results   │
│  Overlay bar   BMD · SFD · AFD · Def · Labels · Diag× Def× │
├──────────────────────────┬──────────────────────────────────┤
│                          │  Properties panel                │
│      Canvas              │  (node / member inspector)       │
│                          ├──────────────────────────────────┤
│                          │  Results panel                   │
│                          │  Displacements · Reactions ·     │
│                          │  Member forces                   │
└──────────────────────────┴──────────────────────────────────┘
```

The **canvas** is the model editor. The **Properties panel** on the right updates to show whatever node or member is selected. Results appear in the three tabs below it after solving.

---

## Building a Model

### Toolbar Modes

| Button | Action |
|--------|--------|
| **Select** | Click to select; drag nodes to reposition |
| **Add Node** | Click anywhere on the canvas to place a node |
| **Add Member** | Click a start node, then click an end node |

The **Member type** dropdown sets the element type for the next member drawn:

| Type | Behaviour |
|------|-----------|
| **Beam** | Full frame element — axial + bending |
| **Bar** | Truss member — axial only, pinned both ends |
| **Pin Left / Pin Right** | Internal hinge at one end (Gerber beam) |

### Grid & Snapping

The canvas grid has major lines every **1 m** and minor lines every **0.25 m**. Nodes snap to the 0.25 m grid automatically — no free-form placement.

### Selecting & Editing

- **Click** a node or member to select it and open its properties.
- **Ctrl + A** selects everything on the canvas.
- **Delete** removes all selected items (members first, then orphaned nodes).
- Drag a node in Select mode to reposition it; connected members follow automatically.

### Undo & Redo

| Action | Shortcut |
|--------|----------|
| Undo | **Ctrl + Z** |
| Redo | **Ctrl + Y** |

Up to 50 undo levels are maintained per session.

---

## Navigation

| Action | Control |
|--------|---------|
| Zoom in / out | **Scroll wheel** |
| Pan | **Middle-mouse drag** |
| Zoom to fit all | **F** |

---

## Properties & Loads

Selecting a node or member opens its inspector in the Properties panel.

### Node Properties

| Field | Description |
|-------|-------------|
| **Support type** | Free · Pin · Roller · Fixed · Spring |
| **Fx, Fy** | Applied nodal forces (N) |
| **Moment** | Applied nodal moment (N·m, CCW positive) |
| **Spring stiffness** | kx, ky, kθ for elastic supports |

### Member Properties

| Field | Description |
|-------|-------------|
| **Element type** | Beam · Bar · Pin Left · Pin Right |
| **E** | Elastic modulus (Pa) |
| **A** | Cross-sectional area (m²) |
| **I** | Second moment of area (m⁴) |
| **UDL w** | Uniform distributed load (N/m, positive = downward) |
| **Subdivisions** | Analysis mesh refinement (default 10, ignored for bars) |

---

## Presets

**Presets** menu provides ready-made models with real European steel sections (S355, EN 1993-1-1):

| Preset | Description |
|--------|-------------|
| **Setback Office Frame** | 6-storey stepped frame, gravity + wind loads, HEB/IPE profiles |
| **Braced Industrial Frame** | 2-storey 4-bay frame with SHS K-bracing |
| **Pratt Truss Bridge** | 12 m span, 6-panel Pratt truss, SHS profiles |
| **Continuous Beam (3-span)** | Fixed–Roller–Roller–Pin, UDL 35 kN/m, IPE 500 |
| **Frame Wizard…** | Generate any regular multi-storey frame by specifying bays, stories, bay width, and storey height |

---

## Running the Analysis

Click **Solve** (or press **F5**). StructLab assembles the global stiffness matrix, solves the system, and recovers all internal forces automatically.

Results are blocked if the model has no members, no supports, or a singular stiffness matrix (e.g. a mechanism). A warning dialog explains the issue before anything is changed.

Click **Clear Results** to remove all overlays and reset the results panel.

---

## Reading Results

### Results Panel (right side)

| Tab | Contents |
|-----|----------|
| **Displacements** | Nodal dx (mm), dy (mm), θ (mrad) |
| **Reactions** | Support forces and moments |
| **Member forces** | N, V, M at element ends for each member |

### Canvas Overlays

Toggle diagrams directly on the canvas using the overlay toolbar buttons:

| Button | Overlay |
|--------|---------|
| **BMD** | Bending moment diagram (sagging below baseline) |
| **SFD** | Shear force diagram |
| **AFD** | Axial force diagram (tension in blue, compression in red) |
| **Def** | Deformed shape (auto-scaled to structure size) |
| **Labels** | Peak force values on each member |
| **Force colours** | Members coloured by axial force sign |

**Diag ×** scales the diagram amplitude. **Def ×** scales the deformation amplification — set to **0** to hide the deformation, increase to exaggerate for presentation.

---

## File Management

| Action | Shortcut | Notes |
|--------|----------|-------|
| New | **Ctrl + N** | Clears canvas and results |
| Open | **Ctrl + O** | Loads a `.slab` file |
| Save | **Ctrl + S** | Saves as `.slab` (JSON format) |

`.slab` files are plain JSON and store all nodes, members, properties, loads, and supports with full round-trip fidelity.

---

## Keyboard Shortcut Reference

| Shortcut | Action |
|----------|--------|
| **F5** | Solve |
| **F** | Zoom to fit |
| **Ctrl + Z** | Undo |
| **Ctrl + Y** | Redo |
| **Ctrl + A** | Select all |
| **Delete** | Delete selected |
| **Ctrl + N** | New model |
| **Ctrl + O** | Open file |
| **Ctrl + S** | Save file |
| **Scroll wheel** | Zoom in / out |
| **Middle-mouse drag** | Pan canvas |

---

*StructLab — Built with Python 3.12 · PyQt6 · NumPy/SciPy · Matplotlib*
