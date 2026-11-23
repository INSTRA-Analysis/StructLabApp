# 6. Solving

## 6.1 Running an analysis

Press **F5**, or click **Solve** on the Analysis tab or the quick buttons at the top right.
StructLab solves the **active load case**; if the case box shows *All Cases*, it asks you to
pick one. Combinations are solved from the combinations dialog (chapter 5.6).

After a successful solve:

- the window switches to the **Results** workspace and shows the deformed shape;
- the status bar gives a summary: the largest deflection (with the member and where along
  it) and the largest bending moment;
- the Results panel fills with displacements, reactions, member forces and design checks.

Any edit to the model discards the results, so they never describe a model that has
since changed: solve again after editing. **Analysis → Clear Results** removes them yourself.

## 6.2 Checks before the solve

Every solve starts with a check of the model. What it finds comes in three levels:

| Level | What happens | Examples |
|---|---|---|
| **Error** | The solve does not run; the message lists what to fix | No supports; no support holding the structure in one direction (it would slide); a node with no member attached; a zero-length member; in a plane frame, nodes off the frame's plane |
| **Warning** | The message lists the findings and asks *Solve anyway?* | Nodes at the same place but not joined; duplicate or overlapping members (their stiffness counts twice); no loads in the case; out-of-plane loads on a plane frame; a plane-frame member with a section rotation β other than 0° or 180° |
| **Note** | The solve runs; the note appears in the status bar afterwards | Space-frame members with no weak-axis I_y or torsion constant J |

When a solve is blocked, the nodes and members behind the errors are selected and the view
zooms to them, so you can see where the problem is.

**Duplicate nodes and members** are the most common cause of wrong answers in imported or
copied geometry. **Model → Check Duplicates…** merges and removes them in one step.

## 6.3 When the structure cannot be solved

If the structure can move without straining any member (a **mechanism**), there is no
answer: the stiffness matrix is singular. StructLab stops, explains the common causes, names
the nodes that move most and zooms to them. Typical causes:

- a missing support, or only rollers, so the whole structure can slide or turn;
- a truss that is not triangulated, so a panel can shear;
- a part of the structure joined to the rest only through pins that let it turn;
- in a space frame, a line of pinned members that can spin about its own axis while a moment
  or eccentric load acts on it.

An **unloaded** free rotation (a node where every member is pinned, with nothing turning it)
is not a mechanism for the purpose of the analysis: StructLab holds it with a tiny spring,
corrects the answer, and the results are unaffected.

## 6.4 Plane frames: out-of-plane loads

A plane frame holds uy, θx and θz at every node. Any load acting out of the plane is
carried by those locks, not by the structure, so it has no effect on the results. If this
happens, the status bar says how much force the locks carried; switch the model to a space
frame (**Analysis → Plane Frame (XZ)** off) to include those loads.

## 6.5 What the analysis is

- **Method**: the direct stiffness method, on the model's members divided into sub-elements.
  Space frames have six freedoms per node; plane frames are solved by the same 3D engine with
  the out-of-plane freedoms held.
- **Linear elastic, first order**: displacements are assumed small, the material stays
  elastic, and equilibrium is written on the undeformed shape. Results for different cases
  can therefore be added, which is what combinations do.
- **Exact along each element**: bending moments, shears and deflections are computed from
  the loads on each element, not interpolated between nodes, so the peak of a diagram is the
  true peak wherever it falls.
- **Not included**: second-order (P-Δ) effects, buckling analysis, cables or tension-only
  members, material non-linearity, dynamics. The design checks deal with member buckling
  where they apply (chapter 8).

Solving is fast: a frame of a few hundred members solves in under a second.
