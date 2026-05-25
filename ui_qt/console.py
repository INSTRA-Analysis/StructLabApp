"""Embedded IPython/Jupyter console dialog for StructLab.

Opens a full RichJupyterWidget (qtconsole) backed by an in-process IPython
kernel.  The live canvas model is pre-injected and a starter example is
auto-executed so the user can see results immediately on open.

Pre-injected names
------------------
    model     — sdk.Model wrapping the current canvas state
    state     — the raw ModelState (nodes, members, load_cases …)
    sdk       — the sdk module (build new models from scratch)
    np        — numpy
    plt       — matplotlib.pyplot (plots open in separate windows)
"""

from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from PyQt6.QtCore import Qt, QTimer

from ui_qt.model_state import ModelState


# ── Welcome banner (printed silently before the first prompt) ─────────────────

_BANNER = """\
\033[36m
  ╔══════════════════════════════════════════════════════════╗
  ║          StructLab — Python Console  (IPython)           ║
  ╠══════════════════════════════════════════════════════════╣
  ║  model   →  sdk.Model wrapping the current canvas        ║
  ║  state   →  raw ModelState  (nodes, members, loads …)    ║
  ║  sdk     →  sdk module  (build new models from scratch)  ║
  ║  np      →  numpy                                        ║
  ║  plt     →  matplotlib.pyplot                            ║
  ╚══════════════════════════════════════════════════════════╝
\033[0m"""


# ── Starter example — auto-executed on open ───────────────────────────────────
# Shown in the console exactly as if the user typed it.
# IPE 300 steel beam, 6 m span, 10 kN/m UDL — textbook simply supported case.

_STARTER_EXAMPLE = """\
# ── Starter example: simply supported beam, 6 m, UDL 10 kN/m ─────────────────
m = sdk.Model()
n0 = m.add_node(0, 0, 0)
n1 = m.add_node(6, 0, 0)
m.pin(n0)
m.roller(n1)
mid = m.add_member(n0, n1, E=210e9, A=6.64e-3, I=8.356e-5)  # IPE 300
m.add_udl(mid, w=10e3)          # 10 kN/m downward

result = m.solve()
print(f"Reactions :  {result.reactions(n0)[1]/1e3:.1f} kN  |  {result.reactions(n1)[1]/1e3:.1f} kN")
print(f"Max moment:  {result.max_moment(mid)/1e3:.3f} kN·m   (wL²/8 = {10*6**2/8:.3f} kN·m)")

fig = result.plot('BMD')
plt.show()\
"""


# ── Console dialog ────────────────────────────────────────────────────────────

class ConsoleDialog(QDialog):
    """Floating dialog containing the embedded IPython console."""

    def __init__(self, model_state: ModelState, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("StructLab — Python Console")
        self.resize(960, 560)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        self._model_state = model_state
        self._widget = _make_console_widget(model_state)

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
        """Full reset — wipe output and restart kernel. Example does not re-run."""
        self._widget.kernel_manager.restart_kernel(now=True)
        self._widget.reset(clear=True)
        QTimer.singleShot(300, lambda: _inject_namespace(self._widget, self._model_state))

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

def _make_console_widget(model_state: ModelState):
    """Build, configure, and return a RichJupyterWidget."""
    import sys, io
    from qtconsole.inprocess import QtInProcessKernelManager
    from qtconsole.rich_jupyter_widget import RichJupyterWidget

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

    widget = RichJupyterWidget()
    widget.kernel_manager = km
    widget.kernel_client = kc
    widget.banner = ""
    widget.style_sheet = _CONSOLE_STYLE
    widget.set_default_style("linux")

    _inject_namespace(widget, model_state)

    # Auto-execute the starter example after the kernel is ready
    QTimer.singleShot(300, lambda: widget.execute(_STARTER_EXAMPLE, hidden=False))

    return widget


def _inject_namespace(widget, model_state: ModelState) -> None:
    """Push live variables into the IPython kernel namespace."""
    import sdk as _sdk
    import numpy as _np
    import matplotlib.pyplot as _plt

    shell = widget.kernel_manager.kernel.shell
    shell.push({
        "sdk":   _sdk,
        "model": _sdk.Model.from_state(model_state),
        "state": model_state,
        "np":    _np,
        "plt":   _plt,
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
