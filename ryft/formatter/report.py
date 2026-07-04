"""The report a formatting run hands back — what got touched, what
didn't, and how long it took."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FormatReport:
    files_scanned: int = 0
    files_formatted: int = 0
    files_skipped: int = 0
    files_ignored: int = 0

    whitespace_chars_removed: int = 0
    blank_lines_collapsed: int = 0

    elapsed_seconds: float = 0.0
    changed_files: list[Path] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"scanned {self.files_scanned}, formatted {self.files_formatted}, "
            f"skipped {self.files_skipped}, ignored {self.files_ignored} "
            f"({self.elapsed_seconds:.2f}s)"
        )
