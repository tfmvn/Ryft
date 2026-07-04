"""/doctor -- health checks, with an optional auto-fix pass."""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import register

if TYPE_CHECKING:
    from ..models import AppContext


@register(
    "doctor",
    description="Health check + auto-repair ('/doctor fix')",
    usage=["/doctor", "/doctor fix"],
)
def cmd_doctor(ctx: "AppContext", args: list[str]) -> None:
    from .. import doctor as doctor_mod, ui

    checks = doctor_mod.run_doctor(ctx)
    ui.render_doctor(checks)

    if not (args and args[0].lower() == "fix"):
        return

    fixable = [c for c in checks if c.status != "ok" and c.auto_fix is not None]
    if not fixable:
        ui.info("Nothing to auto-fix.")
        return

    for check in fixable:
        ok = False
        try:
            ok = bool(check.auto_fix())
        except Exception as exc:  # a fix routine must never crash /doctor
            ui.error(f"Fix for '{check.name}' failed: {exc}")
            continue
        if ok:
            ui.log_activity(ctx, f"Fixed: {check.name}", "success")
        else:
            ui.log_activity(ctx, f"Could not fix: {check.name}", "warn")

    ui.info("Re-running checks…")
    ui.render_doctor(doctor_mod.run_doctor(ctx))
