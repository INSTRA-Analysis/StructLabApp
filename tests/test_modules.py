"""Analysis modules: one registry (ui_qt/modules.py) drives the commands, the ribbon's Modules
tab, the classic Modules menu and the start page.  A 'coming soon' module opens its card; a
module with an entry runs it through ModuleContext."""

import dataclasses
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from ui_qt import modules as mod
from ui_qt.icons import icon_path


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_registry_is_consistent():
    keys = [m.key for m in mod.MODULES]
    assert len(keys) == len(set(keys)) and "static" not in keys
    for m in mod.MODULES + (mod.STATIC_ANALYSIS,):
        assert m.status in mod.STATUSES, m.key
        assert icon_path(m.icon) is not None, m.icon
        assert m.summary and m.title and m.hue.startswith("#")
    assert {m.key: m.status for m in mod.MODULES} == {"dynamics": "coming_soon", "plates": "coming_soon"}


def test_coming_soon_is_not_runnable_and_groups_together():
    for m in mod.MODULES:
        assert not m.runnable
        assert m.ribbon_group == "Coming soon"
        assert m.tooltip.startswith(f"{m.title} — Coming soon")
    live = dataclasses.replace(mod.module("dynamics"), status="available", entry=lambda ctx: None)
    assert live.runnable and live.ribbon_group == "Dynamics"


def test_card_lists_the_scope_and_needs(qapp):
    from PyQt6.QtWidgets import QLabel
    from ui_qt.module_card import ModuleCard
    card = ModuleCard(mod.module("dynamics"))
    text = " ".join(lbl.text() for lbl in card.findChildren(QLabel))
    assert "Response spectrum analysis" in text and "member densities" in text
    assert "Coming soon" in text


@pytest.fixture
def win(qapp, monkeypatch):
    from ui_qt.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_show_welcome", lambda self: None)
    monkeypatch.setattr(MainWindow, "_check_autosave_recovery", lambda self: False)
    w = MainWindow()
    yield w
    w._is_dirty = False
    w.close()


def test_every_module_has_a_command_in_the_ribbon(win):
    bar = getattr(win, "_ribbon", None)
    for m in mod.MODULES:
        act = win._act[m.command_key]
        assert act.text().replace("&&", "&") == m.title and m.summary in act.toolTip()
        if bar is not None:
            page = bar.page("Modules")
            placed = {b.defaultAction() for g in page.groups for b in g.buttons}
            assert act in placed


def test_a_coming_soon_module_opens_its_card(win, monkeypatch):
    import ui_qt.module_card as card
    shown = []
    monkeypatch.setattr(card, "show_module_card", lambda parent, spec: shown.append(spec.key))
    win._act["module_plates"].trigger()
    assert shown == ["plates"]


def test_an_available_module_runs_with_a_context(win, monkeypatch):
    seen = []
    live = dataclasses.replace(mod.module("dynamics"), status="available",
                               entry=lambda ctx: seen.append((ctx.model_state, ctx.results)))
    monkeypatch.setitem(mod._BY_KEY, "dynamics", live)
    win._act["module_dynamics"].trigger()
    assert seen == [(win._scene.model_state, None)]
