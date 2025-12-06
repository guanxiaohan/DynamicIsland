# dynamic_tasks.py
from __future__ import annotations
import asyncio
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional, Dict

from PySide6.QtCore import QObject, Signal, QThread, QTimer, Qt
from concurrent.futures import ThreadPoolExecutor, Future

# ---------- small helpers ----------
def _make_id() -> str:
    return uuid.uuid4().hex

# ---------- Event loop thread (runs asyncio loop in background thread) ----------
class EventLoopThread(QThread):
    """Run an asyncio event loop in a dedicated thread.
    Provides submit(coro) -> concurrent.futures.Future (asyncio.Future wrapped)."""
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._started = threading.Event()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._started.set()
        try:
            self.loop.run_forever()
        finally:
            # cleanup tasks
            pending = asyncio.all_tasks(loop=self.loop)
            if pending:
                for t in pending:
                    t.cancel()
                self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self.loop.close()

    def submit_coro_threadsafe(self, coro) -> asyncio.Future:
        """Submit coro to the loop; must be called after thread started."""
        if not self._started.is_set():
            raise RuntimeError("Event loop thread not started")
        return asyncio.run_coroutine_threadsafe(coro, self.loop)  # returns concurrent.futures.Future # type: ignore

    def stop(self, timeout: float = 2.0):
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.wait(int(timeout * 1000))

# ---------- Signals for returning results to main thread ----------
class TaskResultEmitter(QObject):
    # (task_id, widget, result, exc)
    finished = Signal(str, object, object, object)


# ---------- Task descriptor ----------
@dataclass
class ScheduledTask:
    id: str
    func: Callable[..., Any]           # either sync function or coroutine factory
    args: tuple
    kwargs: dict
    is_coroutine: bool
    owner: Optional[Any] = None             # <--- NEW: who owns this task (e.g. the widget)
    coalesce_key: Optional[str] = None
    debounce_ms: Optional[int] = None
    periodic_ms: Optional[int] = None
    last_future: Optional[Any] = None    # Future or concurrent.futures.Future
    cancelled: bool = False
    scheduled_time: float = 0.0
    priority: int = 0


# ---------- The scheduler itself ----------
class TaskScheduler(QObject):
    """Per-panel task scheduler.
    - Runs sync functions on a ThreadPoolExecutor.
    - Runs coroutine functions on a dedicated EventLoopThread.
    - Emits results on TaskResultEmitter.finished in the main thread.
    - Supports schedule_once, schedule_periodic, debounce, coalesce (replace last)."""

    def __init__(self, parent: Optional[QObject] = None, max_workers: int = 2, use_async_loop: bool = True):
        super().__init__(parent)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.use_async_loop = use_async_loop
        self.loop_thread: Optional[EventLoopThread] = None
        if use_async_loop:
            self.loop_thread = EventLoopThread(self)
            self.loop_thread.start()
            # wait until loop initialized
            self.loop_thread._started.wait(timeout=2.0)
        self.emitter = TaskResultEmitter(self)
        # maps
        self.tasks: Dict[str, ScheduledTask] = {}
        self.coalesce_map: Dict[str, str] = {}  # coalesce_key -> task_id
        self.debounce_timers: Dict[str, QTimer] = {}  # task_id -> QTimer
        self.periodic_timers: Dict[str, QTimer] = {}
        self._lock = threading.Lock()

    def _wrap_sync(self, task_id: str, func: Callable, args, kwargs):
        try:
            result = func(*args, **kwargs)
            self.emitter.finished.emit(task_id, getattr(func, "__self__", None), result, None)
        except Exception as e:
            self.emitter.finished.emit(task_id, getattr(func, "__self__", None), None, e)

    def _schedule_sync(self, sched: ScheduledTask):
        # submit to ThreadPoolExecutor
        fut: Future = self.executor.submit(self._sync_executor_wrapper, sched)
        sched.last_future = fut
        return fut

    def _sync_executor_wrapper(self, sched: ScheduledTask):
        try:
            result = sched.func(*sched.args, **sched.kwargs)
            # Use sched.owner to indicate which widget/owner
            self.emitter.finished.emit(sched.id, sched.owner, result, None)
        except Exception as e:
            self.emitter.finished.emit(sched.id, sched.owner, None, e)


    def _schedule_coro(self, sched: ScheduledTask):
        if not self.loop_thread:
            raise RuntimeError("Scheduler not configured with async loop")
        # allow func to be a coroutine or a callable returning a coroutine
        coro = sched.func(*sched.args, **sched.kwargs) if callable(sched.func) else sched.func
        cfut = self.loop_thread.submit_coro_threadsafe(coro)
        sched.last_future = cfut
        # attach callback to move result to emitter once done (done callback runs in threadpool thread)
        def _on_done(f):
            try:
                res = f.result()
                self.emitter.finished.emit(sched.id, sched.owner, res, None)
            except Exception as e:
                self.emitter.finished.emit(sched.id, sched.owner, None, e)
        cfut.add_done_callback(_on_done)
        return cfut

    # Public API -----------------------------------------------------

    def scheduleOnce(self,
                    func: Callable[..., Any],
                    *args,
                    is_coroutine: bool = False,
                    owner: Optional[Any] = None,        # <-- new
                    coalesce_key: Optional[str] = None,
                    debounce_ms: Optional[int] = None,
                    priority: int = 0,
                    **kwargs) -> str:
        task_id = _make_id()
        sched = ScheduledTask(
            id=task_id,
            func=func,
            args=args,
            kwargs=kwargs,
            is_coroutine=is_coroutine,
            owner=owner,
            coalesce_key=coalesce_key,
            debounce_ms=debounce_ms,
            priority=priority,
            scheduled_time=time.time())
        with self._lock:
            self.tasks[task_id] = sched
            if coalesce_key:
                # if another pending with this key, mark it canceled (we keep last)
                prev_id = self.coalesce_map.get(coalesce_key)
                if prev_id:
                    prev = self.tasks.get(prev_id)
                    if prev and not prev.cancelled and not prev.last_future:
                        prev.cancelled = True
                    # replace map
                self.coalesce_map[coalesce_key] = task_id

            if debounce_ms:
                # create/replace debounce timer
                timer = self.debounce_timers.get(task_id)
                if timer:
                    timer.stop()
                else:
                    timer = QTimer(self)
                    timer.setSingleShot(True)
                    self.debounce_timers[task_id] = timer

                def _on_debounce():
                    # remove debounce timer
                    self.debounce_timers.pop(task_id, None)
                    # actually dispatch
                    self._dispatch(sched)

                timer.timeout.connect(_on_debounce)
                timer.start(debounce_ms)
                return task_id

            # immediate dispatch
            self._dispatch(sched)
            return task_id

    def schedulePeriodic(self,
                        func: Callable[..., Any],
                        interval_ms: int,
                        *args,
                        is_coroutine: bool = False,
                        owner: Optional[Any] = None,
                        coalesce_key: Optional[str] = None,
                        priority: int = 0,
                        **kwargs) -> str:
        task_id = _make_id()
        sched = ScheduledTask(
            id=task_id,
            func=func,
            args=args,
            kwargs=kwargs,
            is_coroutine=is_coroutine,
            owner=owner,
            coalesce_key=coalesce_key,
            periodic_ms=interval_ms,
            priority=priority,
            scheduled_time=time.time()
        )

        with self._lock:
            self.tasks[task_id] = sched

            timer = QTimer(self)
            timer.setInterval(interval_ms)
            timer.setSingleShot(False)

            def _on_tick():
                # optionally skip if previous still running
                # if sched.last_future is not None:
                #     # if still running, we skip to avoid piling up; alternative: queue
                #     return
                self._dispatch(sched)

            timer.timeout.connect(_on_tick)
            timer.start()
            self.periodic_timers[task_id] = timer
            return task_id

    def _dispatch(self, sched: ScheduledTask):
        if sched.cancelled:
            return
        # if coalesced, check if this is the last-winner
        if sched.coalesce_key:
            last = self.coalesce_map.get(sched.coalesce_key)
            if last != sched.id:
                sched.cancelled = True
                return

        # dispatch to correct executor
        if sched.is_coroutine:
            try:
                self._schedule_coro(sched)
            except Exception as e:
                self.emitter.finished.emit(sched.id, getattr(sched.func, "__self__", None), None, e)
        else:
            self._schedule_sync(sched)

    def cancel(self, task_id: str):
        with self._lock:
            sched = self.tasks.get(task_id)
            if not sched:
                return
            sched.cancelled = True
            # stop periodic timer if any
            t = self.periodic_timers.pop(task_id, None)
            if t:
                t.stop()
                t.deleteLater()
            # stop debounce timer
            dt = self.debounce_timers.pop(task_id, None)
            if dt:
                dt.stop()
                dt.deleteLater()
            # cancel futures
            fut = sched.last_future
            if fut:
                try:
                    fut.cancel()
                except Exception:
                    pass
            # remove coalesce map
            if sched.coalesce_key and self.coalesce_map.get(sched.coalesce_key) == task_id:
                self.coalesce_map.pop(sched.coalesce_key, None)
            # finally remove
            self.tasks.pop(task_id, None)

    def shutdown(self, wait: bool = True):
        # stop timers
        for t in list(self.periodic_timers.values()):
            t.stop()
            t.deleteLater()
        self.periodic_timers.clear()
        for t in list(self.debounce_timers.values()):
            t.stop()
            t.deleteLater()
        self.debounce_timers.clear()
        # cancel outstanding tasks
        for tid in list(self.tasks.keys()):
            self.cancel(tid)
        # shutdown executor
        self.executor.shutdown(wait=wait)
        # stop event loop thread
        if self.loop_thread:
            self.loop_thread.stop()
            self.loop_thread = None
