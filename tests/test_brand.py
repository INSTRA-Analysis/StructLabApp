"""The instrahub mark: it renders at every size, the app icon and the packaged .ico carry it."""

import struct

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def _opaque_share(image):
    w, h = image.width(), image.height()
    hits = sum(1 for x in range(w) for y in range(h) if image.pixelColor(x, y).alpha() > 0)
    return hits / (w * h)


def test_mark_svg_is_valid_and_renders(qapp):
    from ui_qt.brand import MARK_SVG, mark_pixmap
    from PyQt6.QtSvg import QSvgRenderer
    assert QSvgRenderer(str(MARK_SVG)).isValid()
    share = _opaque_share(mark_pixmap(64).toImage())
    assert 0.2 < share < 0.9                     # drawn, on a transparent ground


def test_mark_survives_its_cached_renderer_being_deleted(qapp):
    """Regression: the cached QSvgRenderer died with a torn-down QApplication and the next
    window crashed (RuntimeError: wrapped C/C++ object has been deleted)."""
    from PyQt6 import sip
    from ui_qt import brand
    sip.delete(brand._mark_renderer())
    assert not brand.mark_pixmap(32).isNull()


def test_hub_is_cyan_and_the_corners_are_clear(qapp):
    from ui_qt.brand import mark_pixmap
    img = mark_pixmap(64).toImage()
    centre = img.pixelColor(32, 32)
    assert centre.blue() > 150 and centre.red() < 80          # the blue-cyan hub
    assert img.pixelColor(1, 1).alpha() == 0


def test_app_icon_has_a_tile_at_every_size(qapp):
    from ui_qt.brand import ICON_SIZES, app_icon, icon_image
    assert {s.width() for s in app_icon().availableSizes()} >= set(ICON_SIZES)
    for size in (16, 256):
        img = icon_image(size)
        assert img.pixelColor(size // 2, 2).alpha() == 255    # dark tile behind the mark


def test_packaged_ico_holds_the_standard_sizes():
    from ui_qt.brand import ICO_PATH, ICON_SIZES
    data = ICO_PATH.read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1)
    sizes = {data[6 + 16 * i] or 256 for i in range(count)}
    assert sizes == set(ICON_SIZES)


def test_the_brand_appears_once_on_the_canvas_not_in_the_results_dock():
    """The canvas watermark is the one brand mark; the Results dock card was removed to give
    the tables room."""
    import ui_qt.panels as panels
    assert not hasattr(panels, "BrandingFooter")
