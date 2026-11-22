"""The start page: choose a module first, then that module's own page.  Static Analysis is
today's start page; a coming-soon module shows what it will do.  The user may skip the
chooser and open the last module used (saved through main_window._preferences)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QPushButton


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(qapp):
    from ui_qt.welcome_dialog import WelcomeDialog
    dlg = WelcomeDialog(None, recent_files=[])
    dlg.show()
    yield dlg
    dlg.close()


def test_the_chooser_comes_first_and_lists_every_module(page):
    from ui_qt.modules import MODULES, STATIC_ANALYSIS
    assert page.current_page == "modules"
    assert [t.spec.key for t in page.module_tiles] == [STATIC_ANALYSIS.key] + [m.key for m in MODULES]
    assert set(page.pages) == {"modules", "static"} | {m.key for m in MODULES}
    assert not page.skip_chooser


def test_every_tile_opens_its_page_and_all_modules_goes_back(page):
    from PyQt6.QtTest import QTest
    for tile in page.module_tiles:
        page.show_page("modules")
        QTest.mouseClick(tile, Qt.MouseButton.LeftButton)
        assert page.current_page == tile.spec.key
        back = next(b for b in page.pages[tile.spec.key].findChildren(QPushButton)
                    if "All modules" in b.text())
        back.click()
        assert page.current_page == "modules"
    assert page.isVisible() and page.choice == "blank"          # browsing chooses nothing


def test_a_coming_soon_page_shows_the_scope_and_leads_to_static(page):
    from ui_qt.modules import module
    from ui_qt.welcome_dialog import _Card
    spec = module("dynamics")
    page.show_page("dynamics")
    text = " ".join(lbl.text() for lbl in page.pages["dynamics"].findChildren(QLabel))
    assert all(line in text for line in spec.scope) and "member densities" in text
    card = next(c for c in page.pages["dynamics"].findChildren(_Card)
                if any("Open Static Analysis" in lbl.text() for lbl in c.findChildren(QLabel)))
    card.clicked.emit()
    assert page.current_page == "static"


def test_static_page_keeps_new_open_templates_and_recent(qapp, tmp_path):
    from ui_qt.welcome_dialog import WelcomeDialog
    dlg = WelcomeDialog(None, recent_files=[str(tmp_path / "missing.slab")],
                        start_module="static", skip_chooser=True)
    assert dlg.current_page == "static" and dlg.skip_chooser and len(dlg.recent_cards) == 1
    dlg._choose("blank:plane")
    assert (dlg.choice, dlg.start_mode) == ("blank", "plane")
    assert WelcomeDialog(None, start_module="no-such-module").current_page == "modules"


def test_the_window_remembers_skip_and_the_last_module(qapp, monkeypatch):
    import ui_qt.main_window as mw
    import ui_qt.welcome_dialog as wd
    from PyQt6.QtWidgets import QDialog
    opened = []

    class FakeDialog:
        CHOOSER = "modules"

        def __init__(self, parent, recent_files, banner_art, start_module, skip_chooser):
            opened.append((start_module, skip_chooser))
            self.skip_chooser, self.current_page = True, "dynamics"     # what the user did

        def exec(self):
            return QDialog.DialogCode.Rejected

    show_welcome = mw.MainWindow._show_welcome
    monkeypatch.setattr(mw.MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(mw.MainWindow, "_check_autosave_recovery", lambda self: False)
    win = mw.MainWindow()
    monkeypatch.setattr(wd, "WelcomeDialog", FakeDialog)
    try:
        show_welcome(win)                   # first run: the chooser, nothing saved yet
        show_welcome(win)                   # next run: straight to the last module
        assert opened == [(None, False), ("dynamics", True)]
    finally:
        win._is_dirty = False
        win.close()
