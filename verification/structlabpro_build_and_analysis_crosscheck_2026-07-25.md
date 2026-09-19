# Cross-Examination Report — StructLabPro: build, analysis process & outcome

- **Date:** 2026-07-25
- **Project:** StructLabPro (`C:\Users\imeng\OneDrive\Documents\StructLabPro`)
- **Stream:** app (FEM structural-analysis desktop application)
- **Work under review:**
  - **Build:** `StructLab.spec` (PyInstaller), `requirements.txt`, `README.md`
  - **Analysis process:** `elements/frame_element.py`, `solver/assembler.py`,
    `solver/linear_solver.py`, `solver/fem_loads.py`
  - **Analysis outcome:** SDK (`sdk.py`), `tests/`, `benchmarks/`

## 1. Scope of check
Verify that (a) the app build is sound and reproducible, (b) the FEM *process* (stiffness
formulation, transformations, load assembly, boundary conditions) is theoretically correct,
and (c) the *numeric outcomes* match independent closed-form solutions. Units are SI base
(N, m, N·m, rad). 2D sign convention: N+ = tension, M+ = sagging.

## 2. Trusted references consulted
- **Closed-form beam solutions** (standard beam theory — Roark's *Formulas for Stress and
  Strain*; Hibbeler, *Structural Analysis*). Formulae used: cantilever `δ=PL³/3EI`,
  `M=PL`; simply-supported UDL `R=wL/2`, `M=wL²/8`; SS central load `δ=PL³/48EI`, `M=PL/4`;
  fixed-fixed UDL `M_end=wL²/12`; propped cantilever UDL `R_prop=3wL/8`, `M_fix=wL²/8`.
  *(Formulae are canonical; specific page/edition UNVERIFIED — not needed, numeric match is exact.)*
- **Matrix stiffness formulation** — McGuire, Gallagher & Ziemian, *Matrix Structural
  Analysis*; Cook, Malkus, Plesha & Witt, *Concepts and Applications of FEA*. Used to check
  the 2D 6×6 and 3D 12×12 element stiffness matrices at the *formula* level.
  *(The code's own comments cite these; matrix form verified by hand against the standard.
  Page/edition UNVERIFIED.)*
- **Independent recomputation** — `scratchpad/indep_check.py` and `probe_3d.py` (values
  hand-derived, not copied from the app's tests).

## 3. Method
1. Hand-verified every non-zero term of the 2D and 3D local stiffness matrices, pin-release
   condensation, transformation matrices, load assembly, and BC partitioning against the
   standard references.
2. Ran the app's own suites in the `lab` conda env: `sdk.py` self-test, `pytest tests/`,
   `benchmarks/run_all.py`.
3. Ran an **independent** closed-form battery (values I control) covering cantilever,
   fixed-fixed, propped cantilever, simply-supported (central load), a 3D case, and a
   global-equilibrium check on a portal frame.
4. Isolated the one anomaly with a focused probe (`probe_3d.py`) to find root cause.

## 4. Findings

### Analysis process (FEM formulation) — CORRECT
| Item checked | Reference | Result |
|---|---|---|
| 2D frame 6×6 stiffness (`_full_local_stiffness_2d`) | EA/L; 12,6,4,2·EI/Lⁿ | Exact match |
| 3D frame 12×12 (axial, torsion GJ/L, I_z & I_y blocks) | McGuire/Cook std. 12×12 | Exact match, incl. negated y-coupling sign |
| Pin-release stiffness (`3EI/L³, 3EI/L², 3EI/L`) | Released-member form | Correct |
| Equivalent nodal loads = −(fixed-end forces), Tᵀ-transformed | Direct stiffness method | Correct |
| BC partition, `R = K·d − F` at restrained DOFs | Direct stiffness method | Correct |

### Analysis outcome (numerics)
| Suite | Result |
|---|---|
| SDK self-test (SS beam UDL) | R=30 kN=wL/2, M=45 kN·m=wL²/8 — exact |
| `pytest tests/` | **110 / 110 passed** (1.76 s) |
| `benchmarks/run_all.py` | **20 / 20 cases, 72/72 quantities ≤ 0.1%** |
| Independent closed-form battery | **14 / 14 valid checks at 0.00 % error** |

Independent detail (all rel. error 0.00 %): cantilever δ=PL³/3EI = 0.012152 m and M=PL=40
kN·m; fixed-fixed M_end=wL²/12=30 kN·m; propped-cant R=3wL/8=22.5 kN, M_fix=wL²/8=37.5
kN·m; SS central δ=PL³/48EI and M=PL/4; portal ΣFx+H≈1e−8 N (equilibrium). Genuine 3D
vertical column (Fx tip load): dx=0.00972127 m = exactly PL³/3EI, reactions −P and −P·L.

## 5. Discrepancies & risks

**F1 — MEDIUM — Silent out-of-plane load dropping on planar 3D models. [RESOLVED 2026-07-25]**
`core/model.py:34` sets 6 DOF/node **only** `if any(n.z != 0.0 …)`; the `mode_3d` flag does
not force it. A model whose nodes are all at z = 0 is therefore solved as 2D (3 DOF/node),
and the assembler's `dpn==3` branch (`solver/assembler.py:41-51`) applies only `fx, fy,
moment_z` — **`fz`, `Mx`, `My` are silently discarded**. `validate_model` has no guard.
Confirmed: `mode_3d=True`, planar geometry, `Fz` tip load → dofs_per_node=3, zero
deflection, zero reaction. **Realistic failure case:** a flat grillage / horizontal floor
grid modelled in the X-Y plane (z=0) with vertical (Z) loads returns *zero* with no warning.
→ *Fix applied:* `validate_model` (`ui_qt/solve_actions.py`) now emits a **warning (does not
block)** when a model with all nodes at z=0 carries any out-of-plane action (nodal Fz/Mx/My
or a `'qz'` member load): the solve proceeds but the user is told the loads are ignored and
the out-of-plane response is zero — chosen for transparency of app use over a hard stop. The
*force-6-DOF* alternative was rejected: the 2D-in-3D embedding provides no torsion/grillage
bending, so it would turn "silently zero" into "silently wrong" — a proper grillage element
is future work. Regression test: `tests/test_out_of_plane_guard.py` (5 cases: warns on Fz /
Mx / qz on planar models without blocking; stays clean for ordinary 2D loads and genuine-3D
loads — no false positives). Verified: full suite **115 passed** (was 110), benchmarks
**20/20 (72/72 ≤0.1%)** — no regression.

**F2 — MEDIUM — `README.md` is stale and will not launch the app. [RESOLVED 2026-07-25]**
README says *"2D structural analysis application"*, lists *"Streamlit — web UI"*, and
instructs `streamlit run ui/app.py` + bare `pip install -r requirements.txt`. Actual app is
**2D *and* 3D**, a **PyQt6 desktop** app entered at `ui_qt/main.py`, built with PyInstaller;
`streamlit` is explicitly **excluded** in the spec and there is no `ui/app.py`. A user
following the README cannot run or build the app.
→ *Fix applied:* `README.md` rewritten to reflect the real app — 2D **and** 3D, PyQt6
desktop (`python ui_qt/main.py`), Python SDK, `pytest tests/`, `benchmarks/run_all.py`,
PyInstaller build from `StructLab.spec`, plus a 2D-vs-3D coordinate note documenting the F1
behaviour. Streamlit/`ui/app.py` references removed.

**F3 — MEDIUM — `requirements.txt` is UTF-16 LE (no BOM). [RESOLVED 2026-07-25]**
First bytes `50 00 79 00 51 00` = `P·y·Q…`. Bare `pip install -r requirements.txt` reads it
as UTF-8 and will choke on the null bytes / mis-parse the specifiers.
→ *Fix applied:* re-saved as UTF-8 (first bytes now `50 79 51 74 36 3E` = `PyQt6>`, no nulls,
no BOM). Verified with `packaging.requirements.Requirement` — all 8 specs parse cleanly.

**F4 — LOW — Build spec `upx=True`. [RESOLVED 2026-07-25]**
UPX compression of the one-folder bundle can trigger AV false-positives and occasionally
corrupts Qt/numpy DLLs.
→ *Fix applied:* `upx=False` in both `EXE` and `COLLECT` (`StructLab.spec`) with an
explanatory comment; also made the module docstring a raw string to clear a pre-existing
`SyntaxWarning` (invalid `\B` escape from a `C:\Builds` path). Spec compiles clean under
`-W error::SyntaxWarning`. (Entry point, excludes, and hidden-imports were already sound, and
the build path is correctly kept out of OneDrive.) A full PyInstaller rebuild was not run —
config-only change.

## 6. Verdict & confidence
- **Verdict:** **PASS-with-caveats.**
  The analysis engine — both *process* and *outcome* — is **correct and strongly verified**:
  textbook-exact stiffness formulation and 0.00 % agreement with independent closed-form
  solutions across 2D and genuine-3D cases (110 unit tests + 20 benchmarks + 14 independent
  checks all pass). Caveats are (F1) a silent out-of-plane-load edge case for planar "3D"
  models, and build/doc hygiene issues (F2 README, F3 requirements encoding, F4 UPX).
- **Confidence:** **High** on engine correctness (multiple independent confirmations); High
  on F1–F3 (reproduced/byte-verified).
- **What would raise confidence further:** a mesh-convergence check on distributed-load BMD
  peaks; a member-level free-body equilibrium check on a multi-member 3D frame; confirming
  the exact edition/clause of the cited texts if a formal citation is needed.

## 7. Follow-ups
1. F1: ~~add a validation guard~~ **DONE** — guard added + regression test, suite green.
2. F3: ~~re-encode `requirements.txt` as UTF-8~~ **DONE** — clean UTF-8, parse-verified.
3. F2: ~~bring `README.md` in line with reality~~ **DONE** — rewritten for PyQt6/SDK/PyInstaller.
4. F4: ~~reconsider `upx=True`~~ **DONE** — `upx=False` in EXE + COLLECT, spec compiles clean.

**All findings F1–F4 resolved. A full PyInstaller rebuild (to confirm the .exe launches with
UPX off) is the one remaining manual smoke-test, outside this environment.**
