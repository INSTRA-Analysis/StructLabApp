"""Screenshots for the StructLab User Guide, taken from the real window (offscreen).

Run from the repository root:  python guide/tools/capture.py
Images are written to guide/images/. Interface preferences, recent files and the autosave
are redirected to a temporary folder, so the user's own settings are never touched.
Re-run after any interface change and rebuild the PDF (guide/tools/build_pdf.py).
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
os.environ["STRUCTLAB_UI"] = "ribbon"

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, QSettings, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QFrame, QMessageBox

IMAGES = ROOT / "guide" / "images"
EXAMPLES = ROOT / "examples"
TOWER = EXAMPLES / "l8c_d30_tower_seminar_optimised.slab"
WINDOW_SIZE = (1440, 900)
ACCENT = QColor("#00b4d8")

app = QApplication(sys.argv)
from ui_qt.theme import apply_theme  # noqa: E402

apply_theme(app)
import ui_qt.main_window as mw  # noqa: E402
import ui_qt.recent_files as rf  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="structlab_guide_"))
mw._preferences = lambda: QSettings(str(_TMP / "prefs.ini"), QSettings.Format.IniFormat)
mw._AUTOSAVE_PATH = _TMP / "autosave.slab"
rf.push = lambda path: None
mw.MainWindow._show_welcome = lambda self: None
mw.MainWindow._check_autosave_recovery = lambda self: False
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)


def settle(rounds: int = 12) -> None:
    """Let Qt lay out and paint."""
    for _ in range(rounds):
        app.processEvents()
        time.sleep(0.02)


def save(image: QImage, name: str) -> None:
    image.save(str(IMAGES / name))
    print("wrote", name)


def open_window(path: Path | None = None):
    win = mw.MainWindow()
    win.resize(*WINDOW_SIZE)
    win.show()
    win._act["selection_hud"].setChecked(False)
    settle()
    if path is not None:
        win._open_file(str(path))
        settle()
    return win


def close_window(win) -> None:
    win._is_dirty = False
    win.close()
    settle(3)


def rect_in_window(win, widget) -> QRect:
    """``widget``'s rectangle in window coordinates."""
    return QRect(widget.mapTo(win, QPoint(0, 0)), widget.size())


def numbered(image: QImage, marks: list[tuple[int, QPointF]]) -> QImage:
    """Draw numbered callout badges (accent circles) on a copy of ``image``."""
    out = image.copy()
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = QFont("Bahnschrift")
    font.setPixelSize(15)
    font.setBold(True)
    p.setFont(font)
    for number, centre in marks:
        r = QRectF(centre.x() - 13, centre.y() - 13, 26, 26)
        p.setPen(QPen(QColor("#0b1118"), 2))
        p.setBrush(ACCENT)
        p.drawEllipse(r)
        p.setPen(QColor("#0b1118"))
        p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), str(number))
    p.end()
    return out


# ── Chapter 1: the start page ────────────────────────────────────────────────────
def capture_start_page() -> None:
    from ui_qt.banner_themes import BANNERS
    from ui_qt.welcome_dialog import WelcomeDialog
    recent = [str(TOWER), str(EXAMPLES / "l8c_d30_tower_3d.slab")]
    dlg = WelcomeDialog(None, recent_files=recent, banner_art=BANNERS[0].make())
    dlg.resize(1280, 800)
    dlg.show()
    settle(30)
    save(dlg.grab().toImage(), "start_page.png")
    dlg.show_page("dynamics")
    settle()
    save(dlg.grab().toImage(), "start_page_module.png")
    dlg.close()


# ── Chapter 2: the window ────────────────────────────────────────────────────────
def solved_tower():
    """The example tower, solved under its first ULS combination, in the Results workspace."""
    win = open_window(TOWER)
    state = win._scene.model_state
    uls = next(c for c in state.combinations if getattr(c, "limit_state", "ULS") == "ULS")
    win._act["util_colours"].setChecked(True)
    win._solve_combination(uls)
    settle()
    win._act["ws_results"].trigger()
    for key in ("ov_bmd", "ov_sfd", "ov_def", "ov_labels"):
        win._act[key].setChecked(False)
    win._act["util_colours"].setChecked(False)
    win._act["util_colours"].setChecked(True)
    win._act["view_sw"].trigger()
    win._view.zoom_to_fit()
    settle(20)
    return win


def capture_window_tour(win) -> None:
    from ui_qt.nav_gizmo import NavGizmo
    shot = win.grab().toImage()
    ribbon = rect_in_window(win, win._ribbon)
    tabs = rect_in_window(win, win._ribbon.tabs)
    last_tab = win._ribbon.tabs.tabRect(win._ribbon.tabs.count() - 1)
    switch = rect_in_window(win, win._ribbon.findChild(QFrame, "ws_switch"))
    viewport = rect_in_window(win, win._view.viewport())
    strips = win._strips
    left, top, right = (rect_in_window(win, s) for s in (strips.left, strips.top, strips.right))
    gizmo_x = viewport.right() - (NavGizmo.MARGIN + NavGizmo.HALF)
    gizmo_y = viewport.top() + NavGizmo.MARGIN + NavGizmo.HALF
    props = rect_in_window(win, win._left_dock)
    results = rect_in_window(win, win._right_dock)
    status = rect_in_window(win, win.statusBar())
    marks = [
        (1, QPointF(tabs.left() + last_tab.right() + 22, tabs.center().y() + 1)),
        (2, QPointF(ribbon.right() - 36, ribbon.center().y() + 14)),
        (3, QPointF(switch.left() - 18, switch.center().y())),
        (4, QPointF(props.left() + props.width() * 0.62, props.top() + 13)),
        (5, QPointF(left.center().x(), left.bottom() + 20)),
        (6, QPointF(top.left() - 18, top.center().y())),
        (7, QPointF(right.left() - 18, right.top() + 14)),
        (8, QPointF(gizmo_x - NavGizmo.HALF - 14, gizmo_y - NavGizmo.HALF + 6)),
        (9, QPointF(results.left() + results.width() * 0.6, results.top() + 12)),
        (10, QPointF(status.left() + status.width() * 0.45, status.center().y())),
    ]
    save(numbered(shot, marks), "window_tour.png")
    # the axis gizmo, enlarged
    half = NavGizmo.HALF + NavGizmo.MARGIN
    crop = shot.copy(int(gizmo_x - half), int(gizmo_y - half), 2 * half, 2 * half)
    save(crop.scaled(2 * crop.width(), 2 * crop.height(),
                     Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation), "axis_gizmo.png")


def used_width(image: QImage, margin: int = 24, min_width: int = 0) -> QImage:
    """``image`` cropped to its buttons: the full-width ribbon is mostly empty on the right.

    Columns of the ribbon body are compared with the background colour at its far right;
    the crop ends ``margin`` pixels after the last column that differs."""
    top, bottom = int(image.height() * 0.35), int(image.height() * 0.85)
    background = image.pixelColor(image.width() - 40, (top + bottom) // 2)
    last = 0
    for x in range(image.width() - 60):
        for y in range(top, bottom, 3):
            c = image.pixelColor(x, y)
            if (abs(c.red() - background.red()) + abs(c.green() - background.green())
                    + abs(c.blue() - background.blue())) > 40:
                last = x
                break
    width = min(image.width(), max(last + margin, min_width))
    return image.copy(0, 0, width, image.height())


def capture_ribbon_tabs(win) -> None:
    for title in ("Home", "Model", "Loads", "Analysis", "Results", "View", "Modules", "Tools"):
        win._ribbon.set_current_tab(title)
        settle(4)
        tabs = win._ribbon.tabs
        tab = tabs.tabRect(tabs.currentIndex())
        tab_end = tabs.mapTo(win._ribbon, tab.topRight()).x() + 24   # keep the active tab's name
        save(used_width(win._ribbon.grab().toImage(), min_width=tab_end),
             f"ribbon_{title.lower()}.png")


def capture_workspaces() -> None:
    """The tower in the Model workspace and the portal frame in Loads (Results: the tour)."""
    win = open_window(TOWER)
    win._act["view_sw"].trigger()
    win._act["ws_model"].trigger()
    win._act["colour_group"].setChecked(True)
    win._groups_dock.show()
    win._groups_dock.raise_()
    win._view.zoom_to_fit()
    settle(20)
    save(win.grab().toImage(), "workspace_model.png")
    close_window(win)

    win = open_window(portal_frame())
    win._act["ws_loads"].trigger()
    win._view.zoom_to_fit()
    settle(20)
    save(win.grab().toImage(), "workspace_loads.png")
    close_window(win)


def portal_frame() -> Path:
    """An 8 m x 4.5 m fixed-base portal: 12 kN/m and 30 kN on the beam, 20 kN sideways."""
    from ui_qt.io import save_model
    from ui_qt.model_state import (DistLoad, MemberLoad, ModelState, NodeLoad, PointLoadData,
                                   SupportType)
    state = ModelState()
    state.analysis_type = "plane_xz"
    n = [state.add_node(0, 0, 0), state.add_node(0, 0, 4.5),
         state.add_node(8, 0, 4.5), state.add_node(8, 0, 0)]
    n[0].support_type = n[3].support_type = SupportType.FIXED
    for i in range(3):
        m = state.add_member(n[i].id, n[i + 1].id)
        m.I_y, m.J = m.I, 1e-5
    state.active_case.member_loads[1] = MemberLoad(
        dist_loads=[DistLoad("w", 12e3, 12e3)], point_loads=[PointLoadData("FORCE", 1 / 3, 30e3)])
    state.active_case.set_node_load(n[1].id, NodeLoad(fx=20e3))
    path = _TMP / "portal_frame.slab"
    save_model(state, str(path))
    return path


# ── Chapters 3 and 4: building a model, supports ─────────────────────────────────
def select_items(win, nodes: tuple[int, ...] = (), members: tuple[int, ...] = ()) -> None:
    """Select nodes / members by id, as a click would, and let the Properties panel update."""
    scene = win._scene
    scene.clearSelection()
    for nid in nodes:
        scene._node_items[nid].setSelected(True)
    for mid in members:
        scene._member_items[mid].setSelected(True)
    settle(6)


def capture_properties() -> None:
    win = open_window(portal_frame())
    select_items(win, members=(1,))
    save(win._left_dock.grab().toImage(), "properties_member.png")
    select_items(win, nodes=(0,))
    save(win._left_dock.grab().toImage(), "properties_node_plane.png")
    close_window(win)

    win = open_window(TOWER)
    base = next(n.id for n in win._scene.model_state.nodes if n.restraints and any(n.restraints))
    select_items(win, nodes=(base,))
    save(win._left_dock.grab().toImage(), "properties_node_space.png")
    close_window(win)


def capture_section_picker() -> None:
    from ui_qt.section_picker import SectionPickerDialog
    dlg = SectionPickerDialog(210e9, 5.38e-3, 8.36e-5)
    dlg.show()
    settle(10)
    save(dlg.grab().toImage(), "section_picker.png")
    dlg.close()


def support_demo(plane: bool) -> Path:
    """One support of each kind: short columns joined by a beam (space), or a beam (plane)."""
    from ui_qt.io import save_model
    from ui_qt.model_state import ModelState, SupportType
    state = ModelState()
    if plane:
        state.analysis_type = "plane_xz"
        kinds = (SupportType.FIXED, SupportType.PIN, SupportType.ROLLER, SupportType.ROLLER_Z,
                 SupportType.SPRING)
        nodes = [state.add_node(1.5 * i, 0, 0) for i in range(len(kinds))]
        for a, b in zip(nodes, nodes[1:]):
            state.add_member(a.id, b.id)
        supported = nodes
    else:
        kinds = (SupportType.FIXED, SupportType.PIN, SupportType.ROLLER, SupportType.ROLLER_Y,
                 SupportType.ROLLER_Z, SupportType.SPRING)
        supported, tops = [], []
        for i in range(len(kinds)):
            base, top = state.add_node(3.0 * i, 0, 0), state.add_node(3.0 * i, 0, 2.5)
            state.add_member(base.id, top.id)
            supported.append(base)
            tops.append(top)
        for a, b in zip(tops, tops[1:]):
            state.add_member(a.id, b.id)
    for node, kind in zip(supported, kinds):
        node.support_type = kind
        if kind == SupportType.SPRING:
            node.spring_kz = 5e6
    path = _TMP / ("supports_plane.slab" if plane else "supports_space.slab")
    save_model(state, str(path))
    return path


def model_crop(win, margin: int = 70) -> QImage:
    """The view's picture cropped to the model's nodes plus ``margin`` pixels."""
    view = win._view
    points = [view.mapFromScene(item.pos()) for item in win._scene._node_items.values()]
    xs, ys = [p.x() for p in points], [p.y() for p in points]
    image = view.viewport().grab().toImage()
    left, top = max(0, min(xs) - margin), max(0, min(ys) - margin)
    right, bottom = min(image.width(), max(xs) + margin), min(image.height(), max(ys) + margin)
    return image.copy(left, top, right - left, bottom - top)


def capture_supports() -> None:
    win = open_window(support_demo(plane=False))
    win._act["view_sw"].trigger()
    win._view.zoom_to_fit()
    settle(20)
    save(model_crop(win), "supports_3d.png")
    win._act["show_restraints"].setChecked(True)
    settle(10)
    save(model_crop(win), "supports_markers.png")
    win._act["show_restraints"].setChecked(False)
    win._act["local_axes"].setChecked(True)
    settle(10)
    save(model_crop(win), "local_axes.png")
    win._act["local_axes"].setChecked(False)
    close_window(win)

    win = open_window(support_demo(plane=True))
    win.resize(1000, 700)                # a narrower view: the symbols keep their pixel size
    settle()
    win._view.zoom_to_fit()
    settle(20)
    save(model_crop(win, margin=50), "supports_plane.png")
    close_window(win)


# ── Chapter 5: loads ─────────────────────────────────────────────────────────────
def capture_loads() -> None:
    from PyQt6.QtWidgets import QTabWidget
    from ui_qt.combinations import CombinationsDialog
    win = open_window(portal_frame())
    win.resizeDocks([win._left_dock], [420], Qt.Orientation.Horizontal)   # room for the tables
    select_items(win, members=(1,))
    tabs = win._left_dock.findChild(QTabWidget)
    tabs.setCurrentIndex(tabs.indexOf(next(tabs.widget(i) for i in range(tabs.count())
                                           if tabs.tabText(i) == "Loads")))
    settle(6)
    save(win._left_dock.grab().toImage(), "properties_member_loads.png")
    close_window(win)

    win = open_window(TOWER)
    dlg = CombinationsDialog(win._scene.model_state, lambda combo: None, None, win)
    dlg.resize(1000, 560)
    dlg.show()
    settle(10)
    save(dlg.grab().toImage(), "combinations.png")
    dlg.close()
    close_window(win)


def main() -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    capture_start_page()
    win = solved_tower()
    capture_window_tour(win)
    capture_ribbon_tabs(win)
    save(win.grab().toImage(), "workspace_results.png")
    close_window(win)
    capture_workspaces()
    capture_properties()
    capture_section_picker()
    capture_supports()
    capture_loads()


if __name__ == "__main__":
    main()
