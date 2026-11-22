"""Spin-box step buttons: the stylesheet draws + / − images, and every image it names exists."""

import re
from pathlib import Path


def test_spin_button_images_exist_and_are_used():
    from ui_qt.theme import STYLESHEET
    urls = re.findall(r'url\("([^"]+)"\)', STYLESHEET)
    spin = [u for u in urls if "/spin/" in u]
    assert {Path(u).name for u in spin} == {"plus.svg", "minus.svg", "plus_dim.svg", "minus_dim.svg"}
    for u in spin:
        assert Path(u).is_file(), u


def test_spin_buttons_render_their_signs():
    """A themed spin box paints visible marks in its step-button column (they were blank)."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication, QDoubleSpinBox
    from ui_qt.theme import apply_theme
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    box = QDoubleSpinBox()
    box.resize(120, 26)
    box.setValue(1.0)
    img = box.grab().toImage()
    column = [img.pixelColor(x, y).lightness() for x in range(img.width() - 14, img.width() - 3)
              for y in range(3, img.height() - 3)]
    assert max(column) > 180                       # light + / − on the dark button
