"""Start-page banner rotation: each start shows the next theme; a pinned banner stays."""

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def store(tmp_path):
    """A private settings file, so tests never touch the user's real preferences."""
    from PyQt6.QtCore import QSettings
    return QSettings(str(tmp_path / "structlab.ini"), QSettings.Format.IniFormat)


def test_rotation_visits_every_banner_once_per_cycle(store):
    from ui_qt import banner_themes as bt
    n = len(bt.BANNERS)
    seen = [bt.choose(store).key for _ in range(2 * n)]
    assert seen[:n] == [b.key for b in bt.BANNERS]       # in theme order
    assert seen[n:] == seen[:n]                            # and round again


def test_pinned_banner_is_shown_every_time_and_rotation_is_untouched(store):
    from ui_qt import banner_themes as bt
    key = bt.BANNERS[-1].key
    bt.set_pinned(key, store)
    assert [bt.choose(store).key for _ in range(3)] == [key] * 3
    assert store.value(bt.KEY_NEXT, None) is None          # pinning does not advance it
    bt.set_pinned(bt.ROTATE, store)
    assert bt.pinned(store) == bt.ROTATE


def test_unknown_or_corrupt_settings_fall_back_safely(store):
    from ui_qt import banner_themes as bt
    store.setValue(bt.KEY_PIN, "no-such-banner")
    store.setValue(bt.KEY_NEXT, "garbage")
    assert bt.pinned(store) == bt.ROTATE
    assert bt.choose(store).key == bt.BANNERS[0].key


def test_every_banner_draws_and_has_a_theme_label(qapp):
    from ui_qt import banner_themes as bt
    from ui_qt.welcome_dialog import _Banner
    for b in bt.BANNERS:
        art = b.make()
        assert art.theme and art.steps > 0 and len(art.fade) == 2
        w = _Banner(art)
        w.resize(1000, 150)
        w.count = art.steps
        img = w.grab()
        assert not img.isNull()
        w.close()


def test_opening_the_start_page_alone_does_not_advance_the_rotation(qapp, monkeypatch, store):
    """Only MainWindow's start-up chooses (and advances); the dialog just shows what it gets."""
    from ui_qt import banner_themes as bt
    from ui_qt.welcome_dialog import WelcomeDialog
    monkeypatch.setattr(bt, "settings", lambda: store)
    WelcomeDialog(None, recent_files=[]).close()
    assert store.value(bt.KEY_NEXT, None) is None
