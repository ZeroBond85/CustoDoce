"""Unit tests for scripts/warmup_streamlit.py — sidebar readiness logic."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.warmup_streamlit import _sidebar_ready


class _FakeLocator:
    def __init__(self, visible: bool):
        self._visible = visible

    def count(self) -> int:
        return 1 if self._visible else 0

    @property
    def first(self):
        return self

    def is_visible(self) -> bool:
        return self._visible

    def filter(self, **kwargs):
        return self


class _FakeApp:
    """Simula um frame Playwright: locator() por seletor."""

    def __init__(self, button_visible: bool = False, link_visible: bool = False):
        self._button = _FakeLocator(button_visible)
        self._link = _FakeLocator(link_visible)

    def locator(self, selector: str):
        if "button:" in selector:
            return self._button
        return self._link


class TestSidebarReady:
    def test_sidebar_button(self):
        assert _sidebar_ready(_FakeApp(button_visible=True))

    def test_sidebar_link(self):
        assert _sidebar_ready(_FakeApp(link_visible=True))

    def test_sidebar_absent(self):
        assert not _sidebar_ready(_FakeApp())
