"""The start page's Modules row: Static Analysis (included, information only) and each module
from the registry; a coming-soon module opens its card and leaves the start page open."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(qapp):
    from ui_qt.welcome_dialog import WelcomeDialog
    dlg = WelcomeDialog(None, recent_files=[])
    yield dlg
    dlg.close()


def test_modules_row_follows_the_registry(page):
    from ui_qt.modules import MODULES, STATIC_ANALYSIS
    keys = [t.spec.key for t in page.module_tiles]
    assert keys == [STATIC_ANALYSIS.key] + [m.key for m in MODULES]
    assert page.module_tiles[0].objectName() == "start_module"          # included: no click
    assert all(t.objectName() == "start_module_soon" for t in page.module_tiles[1:])


def test_clicking_a_coming_soon_module_opens_its_card(page, qapp, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    import ui_qt.module_card as card
    shown = []
    monkeypatch.setattr(card, "show_module_card", lambda parent, spec: shown.append((parent, spec.key)))
    page.show()
    static, dynamics = page.module_tiles[0], page.module_tiles[1]
    QTest.mouseClick(static, Qt.MouseButton.LeftButton)
    QTest.mouseClick(dynamics, Qt.MouseButton.LeftButton)
    assert shown == [(page, "dynamics")]
    assert page.isVisible() and page.choice == "blank"                   # start page stays open
