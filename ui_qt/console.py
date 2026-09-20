"""Embedded IPython/Jupyter console dialog for StructLab.

Opens a full RichJupyterWidget (qtconsole) backed by an in-process IPython
kernel. The live canvas model is pre-injected — edits made through `state`
or `model` mutate the actual open model, and `refresh()` redraws the canvas
from it (see main_window._refresh_after_console_edit).

Pre-injected names
------------------
    model     — sdk.Model wrapping the current canvas state (same object,
                not a copy — model.solve() and state edits both act on the
                live model)
    state     — the raw ModelState (nodes, members, load_cases …)
    sdk       — the sdk module (build new models from scratch)
    np        — numpy
    plt       — matplotlib.pyplot (plots open in separate windows)
    refresh   — redraw the canvas from `state`/`model` after editing it,
                clear any stale solve results/overlays, and re-frame the
                view on the whole model
    solve     — run the app's own Solve on the canvas model: fills the
                results panel and draws the BMD/SFD/AFD/Deformed overlays
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt, QTimer

from ui_qt.model_state import ModelState


# ── Welcome banner (printed silently before the first prompt) ─────────────────

_BANNER = """\
\033[36m
  ╔══════════════════════════════════════════════════════════╗
  ║          StructLab — Python Console  (IPython)           ║
  ╠══════════════════════════════════════════════════════════╣
  ║  model    →  sdk.Model wrapping the LIVE canvas model     ║
  ║  state    →  raw ModelState  (nodes, members, loads …)    ║
  ║  sdk      →  sdk module  (build new models from scratch)  ║
  ║  np       →  numpy                                        ║
  ║  plt      →  matplotlib.pyplot                            ║
  ║  solve()  →  run the app's Solve, diagrams on canvas      ║
  ║  refresh()→  redraw canvas, re-frame view, clear stale data║
  ╚══════════════════════════════════════════════════════════╝
\033[0m"""


# ── Console dialog ────────────────────────────────────────────────────────────

class ConsoleDialog(QDialog):
    """Floating dialog containing the embedded IPython console."""

    def __init__(
        self,
        model_state: ModelState,
        refresh_cb: Callable[[], None] | None = None,
        solve_cb: Callable[[], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("StructLab — Python Console")
        self.resize(960, 560)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        self._model_state = model_state
        self._refresh_cb = refresh_cb
        self._solve_cb = solve_cb
        self._widget = _make_console_widget(model_state, refresh_cb, solve_cb)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._widget)
        layout.addLayout(self._build_status_bar())

    def _build_status_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setContentsMargins(8, 4, 8, 4)

        info = QLabel(
            "In-process IPython kernel  ·  Tab = complete  ·  "
            "Ctrl+L = clear  ·  Ctrl+C = interrupt"
        )
        info.setStyleSheet("color: #777; font-size: 11px;")
        bar.addWidget(info)
        bar.addStretch()

        for label, slot in [("Clear", self._clear),
                             ("Restart kernel", self._restart_kernel)]:
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.setStyleSheet(
                "QPushButton { background:#2a2a2a; color:#ccc; border:1px solid #444;"
                "  border-radius:3px; padding:0 8px; font-size:11px; }"
                "QPushButton:hover { background:#3a3a3a; }"
            )
            btn.clicked.connect(slot)
            bar.addWidget(btn)

        return bar

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _clear(self) -> None:
        """Full reset — wipe output and restart kernel."""
        self._widget.kernel_manager.restart_kernel(now=True)
        self._widget.reset(clear=True)
        QTimer.singleShot(
            300,
            lambda: _inject_namespace(
                self._widget, self._model_state, self._refresh_cb, self._solve_cb
            ),
        )

    def _restart_kernel(self) -> None:
        """Full reset — identical to Clear."""
        self._clear()

    def closeEvent(self, event) -> None:
        try:
            self._widget.kernel_client.stop_channels()
            self._widget.kernel_manager.shutdown_kernel(now=True)
        except Exception:
            pass
        super().closeEvent(event)


# ── Factory helpers ───────────────────────────────────────────────────────────

def _make_console_widget(
    model_state: ModelState,
    refresh_cb: Callable[[], None] | None,
    solve_cb: Callable[[], None] | None = None,
):
    """Build, configure, and return a RichJupyterWidget."""
    import sys, io
    from qtconsole.inprocess import QtInProcessKernelManager, QtInProcessRichJupyterWidget

    # In windowed PyInstaller builds sys.stdout/stderr are None.
    # IPython flushes them during kernel init, so provide a buffer.
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()

    km = QtInProcessKernelManager()
    km.start_kernel(show_banner=False)
    km.kernel.gui = "qt"

    kc = km.client()
    kc.start_channels()

    # QtInProcessRichJupyterWidget (not the plain RichJupyterWidget) — its
    # _is_complete() checks completeness synchronously against the in-process
    # kernel's shell. The plain widget's _is_complete() instead round-trips an
    # async is_complete request meant for an out-of-process kernel; against an
    # in-process one that reply never lands in time, so it always falls back
    # to "incomplete" and every Enter just inserts a newline instead of
    # executing — which is exactly the bug this fixes.
    widget = QtInProcessRichJupyterWidget()
    widget.kernel_manager = km
    widget.kernel_client = kc
    widget.banner = ""
    widget.style_sheet = _CONSOLE_STYLE
    widget.set_default_style("linux")

    _inject_namespace(widget, model_state, refresh_cb, solve_cb)

    return widget


def _inject_namespace(
    widget,
    model_state: ModelState,
    refresh_cb: Callable[[], None] | None,
    solve_cb: Callable[[], None] | None = None,
) -> None:
    """Push live variables into the IPython kernel namespace."""
    import sdk as _sdk
    import numpy as _np
    import matplotlib.pyplot as _plt

    def _refresh() -> None:
        if refresh_cb is None:
            print("refresh() is unavailable — no canvas is attached to this console.")
            return
        refresh_cb()
        print(f"refresh(): canvas now shows {len(model_state.nodes)} node(s), "
              f"{len(model_state.members)} member(s).")

    def _solve() -> None:
        if solve_cb is None:
            print("solve() is unavailable — no canvas is attached to this console.")
            return
        solve_cb()

    shell = widget.kernel_manager.kernel.shell
    shell.push({
        "sdk":     _sdk,
        "model":   _sdk.Model.from_state(model_state),
        "state":   model_state,
        "np":      _np,
        "plt":     _plt,
        "refresh": _refresh,
        "solve":   _solve,
    })

    # Register %paste as a magic that reads from the Qt clipboard,
    # since the default terminal %paste is unavailable in embedded kernels.
    def _paste_magic(line):
        from PyQt6.QtWidgets import QApplication
        text = QApplication.clipboard().text()
        if text.strip():
            shell.run_cell(text)
        else:
            print("Clipboard is empty.")

    shell.register_magic_function(_paste_magic, magic_kind="line", magic_name="paste")

    shell.run_cell(f"print('''{_BANNER}''')", store_history=False)


# ── Stylesheet ────────────────────────────────────────────────────────────────

_CONSOLE_STYLE = """
QPlainTextEdit, QTextEdit {
    background-color: #1e1e1e;
    color: #d4d4d4;
    font-family: "Consolas", "Cascadia Code", "Courier New", monospace;
    font-size: 12px;
    border: none;
}
"""
