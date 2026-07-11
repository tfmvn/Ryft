"""Background service framework.

Ryft keeps slow work off the UI thread. A `Service` is a long-lived worker; the
simplest kind, `PollingService`, runs `tick()` on a fixed interval in a daemon
thread until stopped. Services never touch the UI directly — they publish
`service_state_changed` / domain events through the `EventBus`, and the UI
reacts. This keeps the dashboard live without polling or blocking paints.

Services are intentionally dumb about *what* they watch; subclass `tick()`.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)


class Service:
    """Base worker. Override `tick()` for the recurring unit of work."""

    name: str = "service"
    interval: float = 5.0

    def __init__(self) -> None:
        self.running = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name=f"ryft:{self.name}", daemon=True)
        self._thread.start()
        logger.debug("service %s started", self.name)

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        logger.debug("service %s stopped", self.name)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - one bad tick must not kill the loop
                logger.exception("service %s tick failed", self.name)
            self._stop.wait(self.interval)

    def tick(self) -> None:  # pragma: no cover - override point
        raise NotImplementedError


class PollingService(Service):
    """Convenience alias: a service whose only job is `tick()` on an interval."""

    def tick(self) -> None:  # pragma: no cover - override in subclasses
        raise NotImplementedError
