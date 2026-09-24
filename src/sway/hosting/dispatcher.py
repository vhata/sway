"""Bounded server-owned bot jobs; persisted pending decisions survive restarts."""

from __future__ import annotations

import logging
import queue
import threading

from sway.hosting.service import HostedService

_LOG = logging.getLogger(__name__)


class BotDispatcher:
    """One process, two workers, at most one outstanding job per table.

    A slow table leaves another worker available. Database revision checks remain
    authoritative if another dispatcher instance accidentally runs concurrently.
    """

    def __init__(self, service: HostedService, *, scan_seconds: float = 5.0) -> None:
        if scan_seconds <= 0:
            raise ValueError("Scan interval must be positive.")
        self.service = service
        self.scan_seconds = scan_seconds
        self._queue: queue.Queue[str] = queue.Queue(maxsize=1024)
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def enqueue(self, game_id: str) -> None:
        with self._lock:
            if game_id in self._pending or self._stop.is_set():
                return
            try:
                self._queue.put_nowait(game_id)
            except queue.Full:
                # The durable scan will discover overflow work again.
                return
            self._pending.add(game_id)

    def start(self) -> None:
        if self._threads:
            return
        self._stop.clear()
        self._threads = [
            threading.Thread(target=self._worker, daemon=True, name=f"sway-bots-{number}")
            for number in range(2)
        ] + [threading.Thread(target=self._scan, daemon=True, name="sway-bot-scan")]
        for thread in self._threads:
            thread.start()

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2)
        if any(thread.is_alive() for thread in self._threads):
            raise RuntimeError("A bot dispatcher worker did not stop.")
        self._threads.clear()
        with self._lock:
            self._pending.clear()
            while not self._queue.empty():
                self._queue.get_nowait()
                self._queue.task_done()

    def _scan(self) -> None:
        while not self._stop.is_set():
            try:
                for game_id in self.service.pending_bot_games():
                    self.enqueue(game_id)
            except Exception as exc:
                _LOG.warning("Bot scan failed (%s).", type(exc).__name__)
            if self._stop.wait(self.scan_seconds):
                return

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                game_id = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            requeue = False
            try:
                requeue = self.service.step_bots(game_id)
            except Exception as exc:
                # Do not include identifiers, decisions, snapshots or exception text.
                _LOG.warning("Bot job failed (%s).", type(exc).__name__)
            finally:
                with self._lock:
                    self._pending.discard(game_id)
                self._queue.task_done()
            if requeue:
                self.enqueue(game_id)
