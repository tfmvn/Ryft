"""Ryft v2 terminal UI.

`theme` holds the design tokens + prompt_toolkit styles; `components` is the
Rich component library; `render` builds on-theme Rich renderables; `tui` is the
full-screen application (dashboard, command palette, overlays). Importing this
package is cheap — it pulls Rich and prompt_toolkit but starts no application.

For backward compatibility the legacy renderer toolkit (`_legacy_ui`) is
re-exported here so existing command modules that do ``from .. import ui`` and
call ``ui.info`` / ``ui.render_diff_summary`` / ``ui.LiveCommitView`` keep
working while the new TUI takes over as the default interactive shell.
"""

from __future__ import annotations

from . import components, render, theme

# ── Backward-compatible legacy renderer toolkit ─────────────────────────────
# `_legacy_ui` lazily imports `ryft.commands` inside functions, so importing it
# here does not create a cycle.
from .._legacy_ui import (  # noqa: E402
    LiveCommitView,
    LivePushView,
    OnboardingProgress,
    RyftApp,
    TaskSpinner,
    confirm,
    console,
    error,
    info,
    log_activity,
    render_activity_full,
    render_ai_output,
    render_code,
    render_completion_screen,
    render_dashboard,
    render_diff_summary,
    render_doctor,
    render_file_diff,
    render_files,
    render_git_changes,
    render_help_command,
    render_help_index,
    render_models,
    render_onboarding_done,
    render_onboarding_welcome,
    render_text,
    render_tree,
    run_model_pull,
    success,
    warn,
)

__all__ = [
    # v2 modules
    "components", "render", "theme",
    # legacy outputs
    "info", "success", "warn", "error", "confirm", "run_model_pull",
    # legacy activity
    "log_activity", "TaskSpinner", "OnboardingProgress",
    # legacy live views
    "LiveCommitView", "LivePushView",
    # legacy render_*
    "render_ai_output", "render_code", "render_completion_screen",
    "render_dashboard", "render_diff_summary", "render_doctor",
    "render_file_diff", "render_files", "render_git_changes",
    "render_help_command", "render_help_index", "render_models",
    "render_text", "render_tree", "render_activity_full",
    "render_onboarding_welcome", "render_onboarding_done",
    # legacy REPL + console
    "RyftApp", "console",
]
