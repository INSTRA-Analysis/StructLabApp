# StructLab User Guide

For StructLab V3.0 and later. The guide is written in steps; chapters not yet written are
listed without links.

1. [Getting started](01_getting_started.md): installing, the start page, plane or space
   frame, saving, a first model
2. [The window](02_the_window.md): ribbon, workspaces, the view, panels, preferences
3. [Building a model](03_building_a_model.md): drawing, selecting, moving and copying,
   member properties, the section library, element types, local axes, checks
4. [Supports and releases](04_supports_and_releases.md): support types, single directions,
   springs, symbols, end releases, stability
5. [Loads](05_loads.md): load cases, nodal and member loads, self-weight, combinations,
   pattern loading
6. [Solving](06_solving.md): running a solve, the checks, mechanisms, what the analysis
   includes
7. [Results](07_results.md): diagrams, result sets, the tables, colouring, the envelope,
   the PDF report
8. [Design checks and Optimise](08_design_and_optimise.md): what each check covers,
   steel angles, crossing bracing, choosing angle sizes by group
9. Worked examples: a portal frame and a transmission tower
10. Reference: files, CSV import, Python SDK, keyboard shortcuts, sign conventions,
    limitations

## Building the guide

From the repository root:

```bash
python guide/tools/capture.py     # re-take the screenshots in guide/images/
python guide/tools/build_pdf.py   # write guide/StructLab_User_Guide.pdf
```

The PDF is not kept in git; it is attached to each release.
