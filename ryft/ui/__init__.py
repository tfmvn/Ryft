"""Ryft Terminal UI — split into focused submodules.

This package replaces the old single-file ``ryft/ui.py``. Every public
name that external code references (``ui.info``, ``ui.RyftApp``,
``ui.LiveCommitView``, etc.) is re-exported here so existing callers work
unmodified. Private helpers live in their respective submodules and are
not re-exported.

Layer layout (no upward dependencies):
  colors  → palette, console, theme, PTK style
  icons   → glyphs, _icon_color (depends on colors)
  pager   → full-screen pager (depends on colors)
  prompt  → info/success/warn/error, confirm, run_model_pull (depends on colors, icons)
  render  → diff renderer, render_* functions, Live views (depends on colors, icons, pager, prompt)
  activity → log_activity, TaskSpinner, onboarding screens, render_activity_full (depends on colors, icons, pager, prompt)
  dashboard → RyftApp REPL, render_dashboard (depends on colors, icons, activity; lazy-imports commands)
"""
from __future__ import annotations

# ── One-line outputs ────────────────────────────────────────────────────────
from .prompt import info, success, warn, error, confirm, run_model_pull  # noqa: A004

# ── Activity, spinner, onboarding screens, activity feed ────────────────────
from .activity import (
    OnboardingProgress,
    TaskSpinner,
    log_activity,
    render_activity_full,
    render_completion_screen,
    render_onboarding_done,
    render_onboarding_welcome,
)

# ── Live views + render_* functions ─────────────────────────────────────────
from .render import (
    LiveCommitView,
    LivePushView,
    render_ai_output,
    render_code,
    render_diff_summary,
    render_doctor,
    render_file_diff,
    render_files,
    render_git_changes,
    render_help_command,
    render_help_index,
    render_models,
    render_text,
    render_tree,
)

# ── REPL + dashboard ─────────────────────────────────────────────────────────
from .dashboard import RyftApp, render_dashboard

# ── Console (used by external code e.g. recovery.py that wraps console.status)
from .colors import console

__all__ = [
    # outputs
    "info", "success", "warn", "error", "confirm", "run_model_pull",
    # activity
    "log_activity", "TaskSpinner",
    # live views
    "LiveCommitView", "LivePushView",
    # render
    "render_ai_output", "render_code", "render_completion_screen",
    "render_dashboard", "render_diff_summary", "render_doctor",
    "render_file_diff", "render_files", "render_git_changes",
    "render_help_command", "render_help_index", "render_models",
    "render_text", "render_tree", "render_activity_full",
    # onboarding
    "OnboardingProgress", "render_onboarding_welcome", "render_onboarding_done",
    # REPL
    "RyftApp",
    # console
    "console",
]
