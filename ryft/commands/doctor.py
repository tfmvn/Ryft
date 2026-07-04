"""Doctor & onboarding/init commands."""
from __future__ import annotations

import logging

from .. import config as config_mod, doctor as doctor_mod, onboarding, ui
from .registry import command

logger = logging.getLogger(__name__)


@command("doctor", "Run health checks.", usage=["/doctor", "/doctor fix"])
def cmd_doctor(ctx, args: list[str]) -> None:
    fix = bool(args) and args[0] == "fix"

    with ui.TaskSpinner(ctx, "Running health checks…") as spin:
        checks = doctor_mod.run_doctor(ctx)
        spin.step("Health checks complete")

    ui.render_doctor(checks)

    if not fix:
        _, warn, fail = doctor_mod.summarize(checks)
        if warn or fail:
            ui.info("Run '/doctor fix' to walk through repairing these automatically.")
        return

    fixable = [c for c in checks if c.status != "ok" and c.auto_fix is not None]
    if not fixable:
        ui.info("Nothing auto-fixable — see the guidance above for anything else.")
        return

    fixed = 0
    for check in fixable:
        ui.info(f"Fixing: {check.name}")
        try:
            ok = check.auto_fix()
        except Exception as exc:
            # auto_fix callables come from a heterogeneous set of
            # recovery.ensure_* helpers (git init, branch creation, model
            # pulls, config writes, ...) — there's no single expected
            # exception type to narrow to here, so this stays a catch-all,
            # but it's logged rather than only shown once and discarded.
            logger.exception("Doctor auto-fix failed for %s", check.name)
            ui.error(f"{check.name}: fix failed — {exc}")
            continue
        if ok:
            fixed += 1
            ctx.activity.add(f"Doctor fixed: {check.name}", "success")
        else:
            ui.warn(f"{check.name}: skipped or still unresolved.")

    ui.success(f"Fixed {fixed}/{len(fixable)} issue(s). Run '/doctor' again to confirm.")


@command("init", "Set up Ryft in this project.", usage=["/init", "ryft init"])
def cmd_init(ctx, args: list[str]) -> None:
    """Explicit onboarding entry point (`ryft init` / `/init`).

    Safe to run repeatedly: if a valid `.src.py` already exists, this
    just says so and stops — it never overwrites configuration without
    an explicit confirmation.
    """
    root = ctx.config.root
    status, detail = config_mod.validate_config(root)

    if status == "valid":
        ui.info(f"Ryft is already initialized here ({root / config_mod.CONFIG_FILENAME}).")
        if not ui.confirm("Reset configuration to defaults anyway?", default=False):
            return
    elif status == "invalid":
        ui.warn(f"A .src.py exists but is invalid: {detail}")
        if not ui.confirm("Reset it to defaults?", default=True):
            return

    cfg, created = onboarding.run_onboarding(root)
    ctx.config = cfg
    if created:
        ui.render_completion_screen(cfg.project.name)
