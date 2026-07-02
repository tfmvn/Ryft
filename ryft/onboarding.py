"""First-run onboarding.

Triggered when Ryft is launched inside a project with no `.src.py`
anywhere in the current directory or its parents. Rather than silently
falling back to defaults or crashing, it walks the user through creating
one — or, if declined, proceeds on in-memory defaults for this session.
"""

from __future__ import annotations

from pathlib import Path

from . import config as config_mod, ui
from .models import Config


def needs_onboarding(start: Path | None = None) -> bool:
    return config_mod.find_root(start) is None


def run_onboarding(cwd: Path) -> tuple[Config, bool]:
    """Run the first-run flow rooted at *cwd*.

    Returns (config, created) — `created` is True only if a `.src.py` was
    actually written, which callers use to decide whether to show the
    "you're ready" completion screen.
    """
    ui.render_onboarding_welcome()

    if not ui.confirm("Create one now?", default=True):
        ui.info("Continuing with built-in defaults for this session.")
        ui.info("Run '/config init' anytime to save a .src.py file.")
        return config_mod.load_config(cwd), False

    with ui.OnboardingProgress() as prog:
        project_name = cwd.name
        prog.step("Project detected")

        try:
            config_mod.init_config(cwd, project_name)
            prog.step("Creating configuration")
        except OSError as exc:
            prog.fail(f"Could not write .src.py: {exc}")
            return config_mod.load_config(cwd), False

        status, detail = config_mod.validate_config(cwd)
        if status == "valid":
            prog.step("Validating")
        else:
            prog.fail(f"Validation failed: {detail}")
            return config_mod.load_config(cwd), False

    ui.render_onboarding_done()
    return config_mod.load_config(cwd), True
