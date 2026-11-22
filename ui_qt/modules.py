"""Analysis modules: one registry for the application's larger add-on capabilities.

A module (modal / dynamic analysis, plate & shell finite elements, ...) is declared ONCE
here as a ModuleSpec.  The command, its ribbon button (tab "Modules") and its classic-menu
entry are generated from this table, so taking a module from placeholder to working tool
means filling in its ``entry`` and changing its ``status`` — no menu or ribbon edits.

Statuses
    coming_soon   the button opens a card saying what the module will do (no entry needed)
    preview       the module runs, under a "preview — not yet verified" notice
    available     the module runs

A module talks to the application only through ``ModuleContext`` (the model, the current
results, the selection, solve, status messages), never MainWindow internals, so its core
can live in its own Qt-free package and be tested on its own — the pattern design_checks.py
and optimise.py already follow.  Nothing here touches the .slab format: a module adds its
own data when it is built.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

STATUSES = ("coming_soon", "preview", "available")
_STATUS_LABEL = {"coming_soon": "Coming soon", "preview": "Preview", "available": ""}


@dataclass(frozen=True)
class ModuleSpec:
    key: str                         # stable id; the command key is "module_<key>"
    title: str                       # button / menu text
    icon: str                        # icon name (StructLab set first, then Lucide)
    hue: str                         # the module's colour: its icon, card accent
    group: str                       # ribbon group once available (e.g. "Dynamics")
    status: str                      # one of STATUSES
    summary: str                     # one or two sentences: what it does
    scope: tuple[str, ...] = ()      # planned / provided capabilities, one line each
    requires: tuple[str, ...] = ()   # what the model needs first (e.g. member densities)
    entry: Callable[["ModuleContext"], None] | None = field(default=None, compare=False)

    @property
    def command_key(self) -> str:
        return f"module_{self.key}"

    @property
    def status_label(self) -> str:
        return _STATUS_LABEL[self.status]

    @property
    def runnable(self) -> bool:
        return self.status != "coming_soon" and self.entry is not None

    @property
    def ribbon_group(self) -> str:
        """Placeholders share one 'Coming soon' group; working modules use their own."""
        return "Coming soon" if self.status == "coming_soon" else self.group

    @property
    def tooltip(self) -> str:
        head = f"{self.title} — {self.status_label}" if self.status_label else self.title
        return f"{head}\n{self.summary}"


# What StructLab does today: shown on the start page beside the modules ("Included"), but
# not a module command — it is the application itself.
STATIC_ANALYSIS = ModuleSpec(
    key="static",
    title="Static Analysis",
    icon="bending-moment",
    hue="#4fb3f6",                   # theme.SKY
    group="Analysis",
    status="available",
    summary="Plane and space frames, load cases and combinations, envelopes, member design "
            "checks and PDF reports.",
)

MODULES: tuple[ModuleSpec, ...] = (
    ModuleSpec(
        key="dynamics",
        title="Dynamic Analysis",
        icon="oscillator",
        hue="#a87ee8",               # theme.RESULT
        group="Dynamics",
        status="coming_soon",
        summary="Natural frequencies and mode shapes of the frame, and the response to "
                "dynamic actions.",
        scope=(
            "Modal analysis: natural frequencies, periods and mode shapes",
            "Masses from member self-weight, plus added nodal masses",
            "Effective modal masses and participation factors",
            "Response spectrum analysis with modal combination (SRSS / CQC)",
            "Mode shapes animated on the canvas",
        ),
        requires=("member densities or added masses",),
    ),
    ModuleSpec(
        key="plates",
        title="Plates & Shells",
        icon="stress-contours",
        hue="#4fd1c5",               # theme.AQUA
        group="Finite Elements",
        status="coming_soon",
        summary="Finite-element plates and shells — slabs, walls and plated parts — meshed "
                "and solved together with the frame.",
        scope=(
            "Plate and shell elements: bending and membrane action",
            "Meshing of slabs and walls from their outline",
            "Plates connected to the frame's beams and columns",
            "Contour plots of displacements, moments and stresses",
        ),
    ),
)

_BY_KEY = {m.key: m for m in MODULES}


def module(key: str) -> ModuleSpec:
    return _BY_KEY[key]


class ModuleContext:
    """What a module may use of the running application — and nothing else."""

    def __init__(self, window) -> None:
        self._win = window

    @property
    def model_state(self):
        """The model being edited (ui_qt.model_state.ModelState)."""
        return self._win._scene.model_state

    @property
    def results(self) -> dict | None:
        """The current solve results (solve_actions.solve_engine's cache), or None."""
        return getattr(self._win, "_solve_cache", None)

    def selection(self) -> tuple[list[int], list[int]]:
        """(selected node ids, selected member ids)."""
        nodes, members = [], []
        for item in self._win._scene.selectedItems():
            if hasattr(item, "node"):
                nodes.append(item.node.id)
            elif hasattr(item, "member"):
                members.append(item.member.id)
        return nodes, members

    def solve(self) -> bool:
        """Run the static solve as the Solve command does; True if results are available."""
        self._win._on_solve()
        return self.results is not None

    def message(self, text: str) -> None:
        """Show a line in the status bar."""
        self._win._sb.showMessage(text)

    @property
    def window(self):
        """The main window, for parenting dialogs only."""
        return self._win


def run_module(window, key: str) -> None:
    """The module's command: run it, or say what is coming."""
    spec = module(key)
    if not spec.runnable:
        from ui_qt.module_card import show_module_card
        show_module_card(window, spec)
        return
    spec.entry(ModuleContext(window))
