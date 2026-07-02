import pytest

from ryft import ui


@pytest.fixture(autouse=True)
def _quiet_console(monkeypatch):
    """Redirect Ryft's Rich console to a null file so tests don't spam
    stdout, and so anything that isn't explicitly monkeypatched still runs
    without touching a real terminal."""
    from rich.console import Console
    import io
    monkeypatch.setattr(ui, "console", Console(file=io.StringIO(), force_terminal=False))
