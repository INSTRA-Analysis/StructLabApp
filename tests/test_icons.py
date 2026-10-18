"""Bundled icon sets: every icon renders, colours follow the theme, licences are shipped."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "ui_qt" / "assets" / "icons"


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _all_names():
    return sorted({p.stem for p in ICONS.rglob("*.svg")})


def test_licence_files_are_bundled_and_noticed():
    assert (ICONS / "lucide" / "LICENSE").read_text(encoding="utf-8").startswith("ISC License")
    notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    assert "Lucide" in notices and "ISC" in notices and "1.48.0" in notices


def test_every_bundled_icon_renders_with_visible_pixels(qapp):
    from ui_qt.icons import icon
    names = _all_names()
    assert len(names) >= 60
    for name in names:
        pm = icon(name).pixmap(24, 24)
        img = pm.toImage()
        opaque = sum(1 for x in range(0, 24, 2) for y in range(0, 24, 2) if img.pixelColor(x, y).alpha() > 0)
        assert opaque > 0, name


def test_unknown_icon_is_empty_not_an_error(qapp):
    from ui_qt.icons import icon
    assert icon("no-such-icon").isNull()


def test_structlab_icons_are_ours_and_found_first(qapp):
    from ui_qt.icons import icon_path
    assert icon_path("member").parent.name == "structlab"
    assert icon_path("save").parent.name == "lucide"


def test_icon_colour_follows_the_theme_and_disabled_state_is_dimmer(qapp):
    from PyQt6.QtGui import QIcon
    from ui_qt.icons import icon
    ic = icon("minus")                                     # a single horizontal stroke
    normal = ic.pixmap(24, 24, QIcon.Mode.Normal).toImage()
    disabled = ic.pixmap(24, 24, QIcon.Mode.Disabled).toImage()
    def brightest(img):
        return max(img.pixelColor(x, 12).lightness() for x in range(24) if img.pixelColor(x, 12).alpha() > 200)
    assert brightest(normal) > brightest(disabled)


def test_label_font_uses_the_application_font_even_when_imported_before_the_app():
    """Regression: a QFont built at import time resolved to the bitmap 'MS Sans Serif' on Windows
    (qt.qpa.fonts: DirectWrite CreateFontFaceFromHDC() failed). Fresh process: the import must
    happen before QApplication exists, as in ui_qt/main.py."""
    import subprocess
    import sys
    code = (
        "import sys; sys.path.insert(0, '.')\n"
        "import ui_qt.main_window\n"
        "from PyQt6.QtWidgets import QApplication\n"
        "from PyQt6.QtGui import QFontInfo\n"
        "app = QApplication([])\n"
        "import ui_qt.canvas_items as ci\n"
        "print(QFontInfo(ci._label_font()).family() == QFontInfo(QApplication.font()).family())\n"
    )
    # The fallback only happens with the native platform plugin, not "offscreen".
    env = {k: v for k, v in os.environ.items() if k != "QT_QPA_PLATFORM"}
    if sys.platform != "win32":
        env["QT_QPA_PLATFORM"] = "offscreen"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                         env=env, timeout=60)
    assert out.stdout.strip().splitlines()[-1] == "True", out.stderr
