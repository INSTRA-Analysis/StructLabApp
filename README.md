# StructLab

A structural analysis application for beams, frames, and trusses — plane and
space — using the Direct Stiffness Method (matrix stiffness analysis). Ships as a
PyQt6 desktop app with an interactive 3D canvas, plus a scriptable Python SDK.

## Features
- One 3D environment (Z up, 6 DOF/node): space frames, and plane frames drawn in the
  XZ plane and analysed in-plane (uy, θx, θz held at every node)
- Frame, beam, and truss (bar) elements; old 2D `.slab` files open as plane frames
- Pin/moment releases, spring supports, rollers (X/Y/Z), fixed & pinned supports
- Point, uniform, linearly varying, and partial distributed loads
- Load cases, load combinations, pattern loading, and result envelopes
- SFD / BMD / AFD diagrams and deformed-shape visualisation (Matplotlib)
- Section library, PDF report export (reportlab), embedded Jupyter console (qtconsole)

## Tech stack
- Python 3.14 (3.12 for the OpenSeesPy benchmarks)
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

m = sl.Model()                      # plane frame in XZ, Z up (Model("space") for 3D)
n0 = m.add_node(0, 0, 0)            # (x, y, z): keep y = 0 in a plane frame
n1 = m.add_node(6, 0, 0)
m.pin(n0)
m.roller(n1)                        # free in X, held vertically
m.add_member(n0, n1, E=210e9, A=6.64e-3, I=8.36e-5)
m.add_udl(0, w=10e3)                # 10 kN/m downward

result = m.solve()
print(result.reactions(n0))         # [Fx, Fy, Fz, Mx, My, Mz]; in-plane: Fx, Fz, My
print(result.max_moment(0))         # peak |M| along member 0
result.plot("BMD")                  # matplotlib Figure
```

See `sdk_examples/` for worked beam and frame scripts. Running `python sdk.py`
executes a self-test (simply-supported beam under UDL) against the closed-form
`R = wL/2`, `M = wL²/8`.

> **Coordinates.** Z is up everywhere. A plane frame lies in the XZ plane; nodes
> off it fail validation (an old 2D script with heights in y is refused rather
> than solved as something else). `Model("space")` is a full 6-DOF space frame
> whatever the coordinates, so a frame laid flat in XY is a horizontal grid.

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
