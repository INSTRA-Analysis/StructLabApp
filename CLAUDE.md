# CLAUDE.md — StructLab Project Context

## What is StructLab?
A **2D and 3D structural analysis desktop application** that solves beams, frames, trusses, and any mixed element structure using the Direct Stiffness Method (DSM). Built in Python with a PyQt6 graphical UI (replacing the earlier Streamlit prototype). Packaged as a standalone `.exe` via PyInstaller — no Python installation required for end users.

## Core Architecture Principle
ALL structure types use a **unified auto-detecting engine**:

**2D mode** (all nodes at z = 0) — 3 DOF/node: [dx, dy, θ_z]
- **Beams** = frame elements with horizontal DOFs restrained
- **Trusses / Bars** = frame elements with moment releases at both ends (pin_i=True, pin_j=True)
- **Frames** = full 3-DOF per node

**3D mode** (any node has z ≠ 0) — 6 DOF/node: [dx, dy, dz, θ_x, θ_y, θ_z]
- Same element types, same pin release logic, same assembler
- Section gains `I_y` (weak-axis), `J` (torsion), and `beta_angle` (section roll)
- Pin releases in 3D condense both θ_y and θ_z at the pinned end

There is ONE solver engine, ONE global assembly routine, ONE `FrameElement` class. Dimensionality is auto-detected from node z-coordinates at solve time — no separate engine per mode.

## Tech Stack
- Python 3.12
- NumPy / SciPy — matrix operations and linear algebra
- Matplotlib — embedded diagram rendering (SFD/BMD/AFD, deformed shape)
- **PyQt6** — primary desktop UI (replaces Streamlit)
- **PyInstaller** — packages app as standalone `.exe` / `.app`
- Streamlit — kept as legacy prototype (`ui/` folder); no longer the primary target
- pytest — testing framework
- Git — version control (local only)

## Project Structure
```
StructLabApp/
├── core/           # Data models: Node, Material, Section, Element, Load, Support, Model
├── elements/       # FrameElement (2D/3D auto-detect + pin releases), BarElement, TrussElement
├── solver/         # Assembler, LinearSolver, Postprocessor, fem_loads
├── ui/             # Legacy Streamlit prototype (kept as reference, not imported)
├── ui_qt/          # PyQt6 desktop application (Phase 6B onwards)
│   ├── main.py            # Entry point, QApplication (65 lines)
│   ├── main_window.py     # Three-panel layout + 3D toolbar (~2,152 lines)
│   ├── solve_actions.py   # validate_model + solve_engine (extracted from main_window)
│   ├── dialogs.py         # KeyboardShortcuts, About, ProjectInfo, DuplicateDialog
│   ├── canvas.py          # QGraphicsScene editor — 2D/3D unified, working planes (~1,036 lines)
│   ├── canvas_items.py    # NodeItem + MemberItem visual classes (~817 lines)
│   ├── canvas_overlay.py  # BMD/SFD/AFD/Deformed drawn as QGraphics overlays (~1,059 lines)
│   ├── projection.py      # Isometric / orthographic az-el projection, inverse mapping
│   ├── model_state.py     # Pure-Python data layer: NodeData, MemberData, LoadCases (~526 lines)
│   ├── model_builder.py   # ModelState → core Model bridge with sub-division (~393 lines)
│   ├── panels.py          # Properties inspector, results table (~1,307 lines)
│   ├── combinations.py    # EN 1990 load combinations manager
│   ├── pattern_loading.py # EN 1992-1-1 pattern loading detection & generation
│   ├── envelope.py        # Envelope results dialog (max/min across combinations)
│   ├── io.py              # JSON .slab save/load (version 2)
│   ├── presets.py         # Template models (academic + showcase), frame_wizard (~1,076 lines)
│   ├── wizards.py         # Beam / Portal / Truss parameterized wizard dialogs
│   ├── pdf_report.py      # Multi-page A4 PDF report generator (matplotlib PdfPages)
│   ├── welcome_dialog.py  # Startup welcome dialog with 2D/3D tab layout
│   ├── recent_files.py    # Persistent recent-files list (~/.structlab/recent_files.json)
│   ├── theme.py           # Dark-theme Qt stylesheet (cyan accent)
│   ├── section_library.py # European steel section database (IPE, HEA, HEB, ...)
│   └── section_picker.py  # Interactive section picker dialog
├── benchmarks/     # 20 benchmark cases (2D + 3D), StructLab vs OpenSeesPy/analytical
│   ├── cases/
│   │   ├── beams_2d.py    # B1–B5 continuous beam cases
│   │   ├── frames_2d.py   # F1–F5 2D frame cases
│   │   ├── trusses_2d.py  # T1–T2 Pratt truss cases
│   │   └── frames_3d.py   # 3D1–3D8 3D frame/cantilever cases
│   ├── run_all.py          # Master runner (all 20 cases)
│   └── sketch.py           # ASCII + matplotlib benchmark sketches
├── Benchmark report/  # Formatted benchmark PDF generator (reportlab)
├── tests/          # pytest test cases (92 tests) — all PASS
├── CLAUDE.md       # THIS FILE
├── README.md
└── requirements.txt
```

---

## Session Safety Rules

### At the START of every session
1. Run `git log --oneline -10` — see recent commits
2. Run `git status` — check for uncommitted work
3. Run `pytest -v` — see which tests pass/fail
4. Read "Current Task" and "Next Steps" below
5. **Write a 3-line state summary before doing any work**
6. If uncommitted changes exist, commit them first: `"WIP: resume from previous session"`

### DURING the session — Incremental Commit Rule
- Break every task into small steps: **one logical change = one commit**
- Step sizes:
  - **Small** — single file, <50 lines → one prompt cycle
  - **Medium** — 2–3 files, <200 lines → one session chunk
  - **Large** — cross-cutting changes, refactors → warn user, propose splitting
- After each step: run relevant tests → commit with descriptive message → move on
- NEVER batch multiple independent changes into one commit
- If a step runs long, stop, test, and commit progress before continuing

### At the END of every session (or when tokens feel low)
1. Commit any pending work, even if incomplete: `"WIP: [done] / [remaining]"`
2. Run `pytest -v` to confirm test count
3. Update "Current Task" and "Next Steps" sections below

---

## Collaboration Rules

### Be direct and push back when needed
- If a proposed feature **does not make engineering sense**, say so clearly and explain why — do not implement it just because the user asked.
- If a proposed feature is **already covered** by existing code or a standard Eurocode workflow, point that out instead of duplicating work.
- If a proposed approach is **overcomplicated** for the problem at hand, say so and propose the simpler alternative.
- If the user's understanding of a **structural engineering concept** is incorrect, correct it with a clear explanation before writing any code.
- Phrase pushback constructively: "That won't work because…" or "We don't need that because X already handles it — here's why." Not just agreement followed by doing the wrong thing.
- **Never implement something you think is wrong or unnecessary** just to avoid disagreement. A short explanation saves more time than bad code.

### Proposals before code
- For any feature that touches more than one file or involves a design decision, **describe the approach and get agreement first**, then implement.
- For quick one-line fixes, just do it; no need to ask.

---

## Coding Standards
- Use **dataclasses** for all core data models
- Use **type hints** on every function and method
- Use **NumPy arrays** (not Python lists) for all matrix/vector operations
- Every module must have a docstring explaining its purpose
- Keep functions short and single-purpose
- Name variables descriptively: `global_stiffness_matrix` not `K_g`
- Use snake_case for functions/variables, PascalCase for classes
- Element stiffness matrices:
  - **2D** (3 DOF/node × 2 nodes = 6 DOFs): 6×6 full, 5×5 one pin, 4×4 both pins
  - **3D** (6 DOF/node × 2 nodes = 12 DOFs): 12×12 full, condensed for pin releases
- Coordinate transformation: standard rotation matrix T (2D: 6×6 block-diagonal; 3D: 12×12 using orthonormal local axes)
- Global assembly uses scatter (connectivity) approach — works for any matrix size

## 3D Projection Conventions (`projection.py`)
- **Coordinate convention**: X, Y = ground plane (horizontal), Z = up (elevation)
- **Projection model**: orthographic az-el (azimuth around Z, elevation above XY plane)
- **Default view**: azimuth = −45°, elevation = 30° (classic SW isometric)
- **Inverse projection**: given screen (sx, sy) + known z → recover (x, y); or given fixed Y/X plane → recover (x, z) / (y, z)
- **Working planes**: XY (lock Z), XZ (lock Y), YZ (lock X), Free (project to z = 0)
- Depth ordering uses painter's algorithm (far-to-near) for correct member occlusion

## Plotting Conventions (display only — do NOT alter calculations)
- **BMD plots**: flip sign when plotting — use `-M` on the y-axis so that:
  - Sagging (positive M, bottom tension) appears **below** the baseline
  - Hogging (negative M, top tension) appears **above** the baseline
  - This is standard structural engineering drawing convention
  - The internal sign convention in `ElementResult` and `SFDBMDResult` stays unchanged (positive M = sagging); only the plot is flipped
- **SFD plots**: no flip — plot V as-is (positive V upward on left face)

## Sign Conventions (critical — do not change without updating tests)
- **2D DOF order per node**: [dx, dy, θ_z] — θ_z is counterclockwise positive
- **3D DOF order per node**: [dx, dy, dz, θ_x, θ_y, θ_z] — all right-hand rule
- **Element load magnitude**: positive = **downward** for transverse loads (LOCAL_Y)
- **FEF (fem_loads.py)**: returns fixed-end force vector in local coords using the downward-positive convention:
  - For downward UDL w: f[1]=+wL/2, f[2]=+wL²/12, f[4]=+wL/2, f[5]=−wL²/12
  - Assembler applies: `F[gi] -= f_global[i]`  (equivalent nodal loads = −FEF)
- **Postprocessor**: internal forces = `k_local @ d_local + FEF` (superposition)
- **Moment sign in ElementResult**: positive M = sagging (bottom fiber in tension)

## Key Engineering Formulas
- **2D** local frame stiffness: 6×6 combining axial (EA/L) and flexural (EI_z/L³) terms
- **3D** local frame stiffness: 12×12 combining axial (EA/L), two bending planes (EI_z/L³, EI_y/L³), and torsion (GJ/L)
- **3D transformation**: T is 12×12, built from orthonormal local axis triad (x̂_local, ŷ_local, ẑ_local) — handles arbitrary orientation and beta_angle roll
- Global element stiffness: k_global = Tᵀ · k_local · T
- System: [K]{d} = {F}, solve for displacements {d}
- Reactions: R = K_rf @ d_f − F_r (where F_r = equiv nodal loads at restrained DOFs)
- Internal forces: f = k_local @ d_local + FEF (superposition of stiffness + load state)

## Testing Strategy
- Every solver feature must have a pytest test
- Validate against known textbook solutions (tolerance: within 0.1%)
- Run `pytest -v` for live pass/fail status — do not maintain a static table here

---

## Development Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | Done | Core engine: FrameElement, assembler, linear solver, simply supported beam test |
| 2 | Done | Beam module: fem_loads, postprocessor, continuous beam test, SFD/BMD |
| 3 | Done | Frame module: portal frames, multi-story, two-bay frames |
| 4 | Done | Truss module: TrussElement wrapper, Pratt truss validation |
| 5 | Done | Visualization & Streamlit UI (legacy prototype) |
| 6A | Done | Engine extensions: pin releases, springs, BarElement, bar-node DOF elimination |
| 6B | Done | PyQt6 scaffold: main window, structural canvas (QGraphicsScene), toolbar |
| 6C | Done | Canvas ↔ solver bridge: ModelState, NodeItem/MemberItem, PropertiesPanel, Solve |
| 6D | Done | Canvas overlay diagrams: BMD/SFD/AFD/Deformed as QGraphicsItem layers |
| 6E | Done | Presets (8 demo + 4 wizards), JSON save/load (.slab v2), File/Presets menus |
| 7 | Done | Benchmarking: 20 cases (2D + 3D), StructLab vs OpenSeesPy/analytical — 0.00% error |
| 8 | Done | PDF reports, welcome dialog, recent files, user guide, packaged .exe, code refactor |
| 9 | Done | **3D engine + 3D UI**: 6-DOF space frame solver, isometric projection, working planes, 3D view presets, 3D overlays (deformed/loads/supports), selection filter, duplicate dialog (Ctrl+D), SFD/BMD peak labels, welcome dialog 2D/3D tabs, 3D benchmarks (3D1–3D8) |

---

## Git Milestones
| Hash | Description |
|------|-------------|
| `538742a` | Pre-3D-only — last clean state with 2D/3D welcome tabs, before UI switch. Safe rollback point. |
| `298d1ca` | 3D-only UI — welcome tabs removed, mode_3d defaults True, _show_welcome simplified. |

To roll back: `git reset --hard <hash>`

---

## Current Task
All phases complete. **92/92 tests passing.** App launchable via `python ui_qt/main.py`.

Active: switched to 3D-only UI (welcome dialog now single flat card row, no 2D/3D tab split).

## Next Steps
1. **Phase 10: Blender-style 3D modeling interface** — improved orbit/pan/zoom, G-grab with axis constraint, E-extrude, numpad-style view recall, 3D grid/workplane visual
2. **Rebuild distribution** — run `pyinstaller StructLab.spec --distpath C:\Builds\StructLab\dist ...` after each release milestone
3. **Presets cleanup** — `presets.py` (~1,076 lines) showcase presets are repetitive; consider a declarative JSON/YAML preset catalog
4. **UI-level integration tests** — save/load roundtrip with load combinations, PDF report generation, welcome dialog
