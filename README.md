# StructLab

A **2D and 3D** structural analysis application for beams, frames, and trusses
using the Direct Stiffness Method (matrix stiffness analysis). Ships as a PyQt6
desktop app with an interactive canvas, plus a scriptable Python SDK.

## Features
- 2D (3 DOF/node) and 3D (6 DOF/node) frame, beam, and truss elements
- Pin/moment releases, spring supports, rollers (X/Y/Z), fixed & pinned supports
- Point, uniform, linearly varying, and partial distributed loads
- Load cases, load combinations, pattern loading, and result envelopes
- SFD / BMD / AFD diagrams and deformed-shape visualisation (Matplotlib)
- Section library, PDF report export (reportlab), embedded Jupyter console (qtconsole)

## Tech stack
- Python 3.12
- NumPy / SciPy — matrix assembly and linear solve
- Matplotlib — force diagrams and plots
- PyQt6 — desktop UI
- reportlab — PDF reports · qtconsole / ipykernel — embedded console
- pytest — tests

## Install

```bash
# (recommended) create an isolated environment first, e.g. conda:
#   conda create -n lab python=3.12 && conda activate lab
pip install -r requirements.txt
```

## Run

```bash
# Launch the desktop app
python ui_qt/main.py

# Run the test suite
pytest tests/

# Run the analytical benchmark suite (closed-form / textbook cases)
python benchmarks/run_all.py
```

## Python SDK

Run analyses from a script or notebook without opening the GUI:

```python
import sdk as sl

m = sl.Model()                      # 2D model (use Model(mode_3d=True) for 3D)
n0 = m.add_node(0, 0, 0)
n1 = m.add_node(6, 0, 0)
m.pin(n0)
m.roller(n1)
m.add_member(n0, n1, E=210e9, A=6.64e-3, I=8.36e-5)
m.add_udl(0, w=10e3)                # 10 kN/m downward

result = m.solve()
print(result.reactions(n0))         # [Fx, Fy, Mz]  (N, N, N·m)
print(result.max_moment(0))         # peak |M| along member 0
result.plot("BMD")                  # matplotlib Figure
```

See `sdk_examples/` for worked beam and frame scripts. Running `python sdk.py`
executes a self-test (simply-supported beam under UDL) against the closed-form
`R = wL/2`, `M = wL²/8`.

> **Coordinates & 2D vs 3D.** A model is solved in 3D (6 DOF/node) only if at
> least one node has a non-zero z coordinate. If every node lies at z = 0 the
> model is solved in 2D — out-of-plane actions (nodal Fz/Mx/My, `qz` member
> loads) are then ignored, and the solver warns you. Model genuinely 3D
> structures (including grillages) with real z-geometry.

## Build (Windows desktop bundle)

Built with PyInstaller from `StructLab.spec`. Build **outside** OneDrive to avoid
file-locking during packaging:

```bat
pyinstaller StructLab.spec ^
  --distpath C:\Builds\StructLab\dist ^
  --workpath C:\Builds\StructLab\build ^
  --noconfirm
```

Output: `C:\Builds\StructLab\dist\StructLab\StructLab.exe` (one-folder bundle).
