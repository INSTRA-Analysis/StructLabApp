"""The start page is one page with one tab per module: Static Analysis (today's start page)
first, then each module from the registry; a coming-soon module's tab shows what it will do.
The page reopens on the tab used last (saved through main_window._preferences)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel


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


def test_one_tab_per_module_static_first_and_open(page):
    from ui_qt.modules import MODULES, STATIC_ANALYSIS
    keys = [t.spec.key for t in page.module_tabs]
    assert keys == [STATIC_ANALYSIS.key] + [m.key for m in MODULES]
    assert set(page.pages) == set(keys)
    assert page.current_page == "static"
    assert [t.selected for t in page.module_tabs] == [True] + [False] * len(MODULES)
    assert [t.soon for t in page.module_tabs] == [False] + [True] * len(MODULES)


def test_clicking_a_tab_shows_it_and_marks_it(page):
    from PyQt6.QtTest import QTest
    for tab in page.module_tabs:
        QTest.mouseClick(tab, Qt.MouseButton.LeftButton)
        assert page.current_page == tab.spec.key
        assert [t.selected for t in page.module_tabs] == [t is tab for t in page.module_tabs]
    assert page.isVisible() and page.choice == "blank"          # browsing chooses nothing


def test_a_coming_soon_tab_shows_the_scope_and_leads_to_static(page):
    from ui_qt.modules import module
    from ui_qt.welcome_dialog import _Card
    spec = module("dynamics")
    page.show_page("dynamics")
    text = " ".join(lbl.text() for lbl in page.pages["dynamics"].findChildren(QLabel))
    assert spec.summary in text and all(line in text for line in spec.scope)
    assert "member densities" in text and "Coming soon" in text
    card = next(c for c in page.pages["dynamics"].findChildren(_Card)
                if any("Open Static Analysis" in lbl.text() for lbl in c.findChildren(QLabel)))
    card.clicked.emit()
    assert page.current_page == "static"


def test_static_tab_keeps_new_open_templates_and_recent(qapp, tmp_path):
    from ui_qt.welcome_dialog import WelcomeDialog
    dlg = WelcomeDialog(None, recent_files=[str(tmp_path / "missing.slab")], start_module="plates")
    assert dlg.current_page == "plates" and len(dlg.recent_cards) == 1
    dlg._choose("blank:plane")
    assert (dlg.choice, dlg.start_mode) == ("blank", "plane")
    assert WelcomeDialog(None, start_module="no-such-module").current_page == "static"


def test_the_window_reopens_the_last_tab(qapp, monkeypatch):
    import ui_qt.main_window as mw
    import ui_qt.welcome_dialog as wd
    from PyQt6.QtWidgets import QDialog
    opened = []

    class FakeDialog:
        def __init__(self, parent, recent_files, banner_art, start_module):
            opened.append(start_module)
            self.current_page = "dynamics"                       # the tab the user ended on

        def exec(self):
            return QDialog.DialogCode.Rejected

    show_welcome = mw.MainWindow._show_welcome
    monkeypatch.setattr(mw.MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(mw.MainWindow, "_check_autosave_recovery", lambda self: False)
    win = mw.MainWindow()
    monkeypatch.setattr(wd, "WelcomeDialog", FakeDialog)
    try:
        show_welcome(win)                   # first run: Static Analysis
        show_welcome(win)                   # next run: the tab used last
        assert opened == ["static", "dynamics"]
    finally:
        win._is_dirty = False
        win.close()
