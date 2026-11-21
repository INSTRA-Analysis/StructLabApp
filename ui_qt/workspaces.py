"""Workspaces: Model · Loads · Results — one click sets the screen up for a stage of work.

Like Blender's workspace tabs, a workspace decides which panels, canvas strips and load
display are shown, and opens the matching ribbon tab. It is switched only from its own
control (the switcher in the ribbon's tab row, or View > Workspace in the classic
interface); clicking a ribbon tab never rearranges the screen.

The three workspaces are shared checkable QActions (keys ``ws_model``, ``ws_loads``,
``ws_results``) so the ribbon switcher and the classic menu show the same state. No
workspace is active at start-up: the window keeps the layout the user left it in until
one is chosen.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtGui import QAction, QActionGroup


@dataclass(frozen=True)
class Workspace:
    key: str
    title: str
    ribbon_tab: str
    results_panels: bool     # Results / Groups docks shown (Results in front)
    results_strip: bool      # the results strip inside the canvas
    show_loads: bool         # load arrows and labels
    tip: str


WORKSPACES: tuple[Workspace, ...] = (
    Workspace("ws_model", "Model", "Model", False, False, True,
              "Build geometry: Properties panel, more room for the canvas"),
    Workspace("ws_loads", "Loads", "Loads", False, False, True,
              "Define load cases and loads: load arrows shown"),
    Workspace("ws_results", "Results", "Results", True, True, False,
              "Read the results: Results panel, diagram strip, load arrows hidden"),
)


def build_workspace_actions(win) -> dict[str, QAction]:
    """One exclusive checkable action per workspace, added to ``win`` and returned by key."""
    group = QActionGroup(win)
    group.setExclusive(True)
    actions: dict[str, QAction] = {}
    for ws in WORKSPACES:
        act = QAction(ws.title, win)
        act.setCheckable(True)
        act.setToolTip(f"{ws.title} workspace — {ws.tip}")
        act.triggered.connect(lambda _c=False, w=ws: apply_workspace(win, w))
        group.addAction(act)
        actions[ws.key] = act
    win._workspace_group = group
    return actions


def apply_workspace(win, ws: Workspace) -> None:
    """Show / hide the panels, strip and loads for ``ws`` and open its ribbon tab."""
    win._left_dock.show()
    if ws.results_panels:
        win._right_dock.show()
        win._groups_dock.show()
        win._right_dock.raise_()
    else:
        win._right_dock.hide()
        win._groups_dock.hide()
    strips = getattr(win, "_strips", None)
    if strips is not None:
        strips.right.setVisible(ws.results_strip)
    win._act["show_loads"].setChecked(ws.show_loads)
    ribbon = getattr(win, "_ribbon", None)
    if ribbon is not None:
        ribbon.set_current_tab(ws.ribbon_tab)
    win._act[ws.key].setChecked(True)
    win._workspace = ws.key
