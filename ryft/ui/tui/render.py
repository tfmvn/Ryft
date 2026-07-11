"""Bridge Rich renderables into prompt_toolkit formatted text.

The TUI is a prompt_toolkit `Application`; the dashboard/panels are composed as
Rich renderables (our component library). We render the Rich tree to an ANSI
string at the current width, then parse it back into prompt_toolkit style fragments via
`to_formatted_text(ANSI(...))`. This lets us keep one rendering pipeline (Rich)
while driving a full-screen PTK app with live, incremental repaints.
"""

from __future__ import annotations

import io
from typing import Any

from prompt_toolkit.formatted_text import ANSI, FormattedText, to_formatted_text
from rich.console import Console

_console = Console(file=io.StringIO(), force_terminal=True, color_system="truecolor")


def to_fragments(renderable: Any, width: int) -> FormattedText:
    """Render `renderable` to prompt_toolkit fragments at `width` columns."""
    _console.width = max(20, width)
    buf = io.StringIO()
    _console.file = buf
    _console.print(renderable)
    ansi = buf.getvalue()
    # `split_format_codes` was removed in prompt_toolkit 3.x; the supported way to
    # parse ANSI escapes back into style fragments is `to_formatted_text(ANSI(...))`.
    return FormattedText(to_formatted_text(ANSI(ansi)))
