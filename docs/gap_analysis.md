# StructLab — Gap Analysis vs Commercial Tools

_Last updated: 2026-05-08_

This document records an honest assessment of where StructLab stands relative to
commercial structural analysis software (SAP2000, ETABS, Robot Structural Analysis,
RFEM, STAAD.Pro, Tekla Structural Designer).  It is intended as a living reference
for prioritising future development.

---

## Analysis engine — solid foundation, narrow scope

### What is correct and validated
- Direct Stiffness Method (DSM) engine, tested against textbook solutions
- Mixed element types: beams, frames, trusses, Gerber beams, spring supports, pin releases
- EN 1990 load combinations with auto-generation (ULS + SLS)
- Pattern loading per EN 1992-1-1 §5.1.3 (alternating + adjacent spans, auto-detected)
- Envelope BMD/SFD across all combinations

### Hard limits vs commercial tools

| Capability | StructLab | Commercial |
|---|---|---|
| Static linear elastic | ✓ | ✓ |
| P-delta (geometric nonlinearity) | ✗ | ✓ |
| Material nonlinearity / plasticity | ✗ | ✓ |
| Modal / frequency analysis | ✗ | ✓ |
| Response spectrum (seismic) | ✗ | ✓ |
| Buckling analysis | ✗ | ✓ |
| Construction sequence | ✗ | ✓ |
| 3D space frame | ✗ — strictly 2D | ✓ |
| Out-of-plane effects / torsion | ✗ | ✓ |

**Most urgent omission:** P-delta. Any slender column or tall frame requires
second-order analysis, and StructLab cannot perform it.

---

## Elements — very limited

StructLab has one element: a 2D frame element (with pin-release and bar variants).
Commercial tools additionally offer:

- **Plate / shell elements** — slabs, shear walls, retaining walls (backbone of building analysis)
- **Solid elements** — foundations, deep beams, connection zones
- **Cable / tension-only elements** — hangers, cable-stayed structures
- **Compression-only elements** — contact, base plates
- **Rigid offsets and semi-rigid connections**

Without plate/shell elements, StructLab cannot model any slab, flat plate, or core wall —
which eliminates the majority of real building structures above a simple frame.

---

## Loads — biggest practical gap for professional use

| Load type | StructLab | Commercial |
|---|---|---|
| UDL / UVL / point forces / moments | ✓ | ✓ |
| **Self-weight** (auto from section density) | **✗** | ✓ |
| Temperature / thermal gradient | ✗ | ✓ |
| Support settlement / prescribed displacement | ✗ | ✓ |
| Pre-stress / post-tension | ✗ | ✓ |
| Moving loads (cranes, trains) | ✗ | ✓ |
| Seismic spectral loads | ✗ | ✓ |
| Code-based wind (EN 1991-1-4 → pressures) | ✗ | ✓ |
| Code-based snow (EN 1991-1-3 → shape factors) | ✗ | ✓ |

**Most critical missing item: self-weight.** Every real project starts with it.
Engineers must currently calculate it manually and input it as a UDL per member —
this is an unacceptable workflow burden for professional use.

---

## Design checks — completely absent

StructLab computes forces and displacements. It does not check capacity.
Commercial tools provide:

- Member utilization ratios (EC3 steel, EC2 concrete, AISC, AS 4100, etc.)
- Automatic section selection ("find the lightest UB that satisfies all checks")
- Deflection limits against SLS criteria (span/250, span/360, etc.)
- Connection design and detailing
- Foundation sizing

Without any design output, StructLab cannot produce a compliant result for
submission to a client or building control authority.

---

## Section and material library

StructLab currently requires the user to input E, A, I directly. This means:

- No built-in steel section database (Arcelor, AISC, British Standard tables)
- No composite section properties
- No concrete section design with reinforcement layout
- No material density (→ no self-weight calculation)
- No temperature-dependent material properties

A basic section picker exists in the codebase but is far below what commercial
tools provide.

---

## Output and reporting

| Output | StructLab | Commercial |
|---|---|---|
| Canvas diagrams (BMD/SFD/AFD/Deformed) | ✓ | ✓ |
| Envelope plots across combinations | ✓ | ✓ |
| Numerical results tables | Basic | Full |
| PDF calculation report | ✗ | ✓ |
| DXF / IFC export | ✗ | ✓ |
| BIM link (Revit, Tekla) | ✗ | ✓ |
| Stamped design output | ✗ | ✓ |

For professional project submission, StructLab produces nothing printable today.

---

## Honest summary

**StructLab is a correct, clean 2D frame analysis engine with good EN 1990
combination handling.** For linear elastic static analysis of beams, frames,
and trusses in 2D, the results are trustworthy and validated.

It is **not yet suitable as a primary tool on a real project** due to the
gaps listed above.

---

## Prioritised roadmap to professional readiness

Listed in order of impact relative to implementation effort:

| Priority | Feature | Why |
|---|---|---|
| 1 | Self-weight from member density | Every real project needs it; quick to add |
| 2 | SLS deflection checks vs span limits | Simplest design check; very high usage |
| 3 | EC3 member utilization (steel beams/columns) | Defines the product category for steel |
| 4 | PDF report export | Required for any professional submission |
| 5 | P-delta geometric nonlinearity | Credibility for real frame design |
| 6 | Built-in steel section database | Eliminates manual property lookup |
| 7 | EC2 reinforced concrete checks | Extends scope to concrete structures |
| 8 | Code-based wind / snow load generation | Removes major manual input burden |
| 9 | 3D space frame (6-DOF per node) | Enables real building models |
| 10 | Plate / shell elements | Enables slabs and shear walls |
