"""Guards for layout bugs that only show up on screen."""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web" / "src"
CSS = (WEB / "styles.css").read_text(encoding="utf-8")
APP = (WEB / "App.tsx").read_text(encoding="utf-8")
ALIVE = (WEB / "Alive.tsx").read_text(encoding="utf-8")


def _block(selector: str) -> str:
    match = re.search(r"(?:^|\n)" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert match, f"missing rule {selector}"
    return match.group(1)


def _z(selector: str) -> int:
    found = re.search(r"z-index:\s*(\d+)", _block(selector))
    assert found, f"{selector} has no z-index"
    return int(found.group(1))


def test_rail_paints_above_the_panels_and_shows_its_labels() -> None:
    assert _z(".rail") > _z(".main")
    assert _z(".rail") > _z(".telemetry")
    # The active-page marker sits outside the rail's edge.
    assert "overflow: visible" in _block(".rail")
    assert "<small>{item.label}</small>" in APP


def test_headline_words_end_visible() -> None:
    words = _block(".alive .word")
    assert "opacity: 0" in words and "forwards" in words
    assert "@keyframes word-in" in CSS
    # Reduced motion must still show the words, not leave them at opacity 0.
    assert re.search(r"prefers-reduced-motion[^{]*\{[^@]*\.alive \.word[^}]*opacity: 1", CSS, re.S)


def test_the_leaned_word_is_clipped_text_not_invisible() -> None:
    lean = _block(".alive .lean")
    assert "background-clip: text" in lean and "-webkit-background-clip: text" in lean
    assert "aria-label={text}" in ALIVE
    assert "<Alive " in APP and "What ORION remembers" in APP


def test_every_phase_has_a_colour() -> None:
    for phase in ("listening", "thinking", "speaking"):
        assert f'[data-phase="{phase}"] .status-chip' in CSS
    assert "document.documentElement.dataset.phase = phase" in APP
