"""Start-page banner rotation: one banner per theme, a different one at each start.

``BANNERS`` lists the banners in rotation order, one per theme so consecutive starts show
different subjects (static → dynamic → finite elements → stability → reliability).
``next_banner`` returns the art to show and advances the rotation; a banner can instead be
pinned (``ui/banner_pin``). Both are stored in QSettings "INSTRA Analysis/StructLab".
Only the chosen banner's art is built, so start-up cost does not grow with the list.

The art classes themselves live in ui_qt/banner_art.py; each has ``theme``, ``steps``,
``fade``, ``tooltip`` and ``paint(painter, origin, step)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import QSettings

ORG, APP = "INSTRA Analysis", "StructLab"
KEY_NEXT = "ui/banner_next"
KEY_PIN = "ui/banner_pin"
ROTATE = ""                       # pin value meaning "rotate"


@dataclass(frozen=True)
class BannerEntry:
    key: str
    title: str                    # shown in the View > Start Page Banner menu
    make: Callable[[], object]    # builds the art (imported lazily)


def _element():
    from ui_qt.banner_art import ElementArt
    return ElementArt()


BANNERS: tuple[BannerEntry, ...] = (
    BannerEntry("element", "Finite elements: the frame element", _element),
)


def entry(key: str) -> BannerEntry | None:
    return next((b for b in BANNERS if b.key == key), None)


def settings() -> QSettings:
    return QSettings(ORG, APP)


def pinned(store: QSettings | None = None) -> str:
    """Key of the pinned banner, or "" when rotating."""
    value = str((store or settings()).value(KEY_PIN, ROTATE) or "")
    return value if entry(value) else ROTATE


def set_pinned(key: str, store: QSettings | None = None) -> None:
    (store or settings()).setValue(KEY_PIN, key if entry(key) else ROTATE)


def choose(store: QSettings | None = None) -> BannerEntry:
    """The banner for this start (pinned, else next in rotation); advances the rotation."""
    store = store or settings()
    pin = pinned(store)
    if pin:
        return entry(pin)
    try:
        index = int(store.value(KEY_NEXT, 0)) % len(BANNERS)
    except (TypeError, ValueError):
        index = 0
    store.setValue(KEY_NEXT, (index + 1) % len(BANNERS))
    return BANNERS[index]


def next_banner(store: QSettings | None = None):
    """The art for this start, built from ``choose``."""
    return choose(store).make()
