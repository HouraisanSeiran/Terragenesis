"""Engineering compute budgets and sampled per-stage current working set."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
import math
import os
from pathlib import Path
import threading
import time


@dataclass(frozen=True)
class ComputeBudget:
    max_pages: int = 64
    max_window_nodes: int = 1337
    max_window_cells: int = 1787569
    max_bucket_cells: int = 100000
    max_bucket_entries: int = 1000000
    max_channel_nodes: int = 128
    max_coupled_intervals: int = 12
    max_local_q_bytes: int = 512 * 1024**2
    max_trace_reserved_bytes: int = 3 * 1024**3
    max_rss_bytes: int = 3 * 1024**3
    max_seconds: float = 1800.0

    def validate(self):
        for name, value in asdict(self).items():
            if name == 'max_seconds':
                if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                    raise ValueError('invalid_budget:' + name)
            elif type(value) is not int or value <= 0:
                raise ValueError('invalid_budget:' + name)

    def check_window(self, records, shape, intervals):
        self.validate()
        if len(records) > self.max_pages:
            raise ValueError('budget_pages')
        if len(shape) != 2 or any(type(v) is not int or v < 2 or v > self.max_window_nodes for v in shape):
            raise ValueError('budget_window_dimension')
        if math.prod(shape) > self.max_window_cells:
            raise ValueError('budget_window_cells')
        if type(intervals) is not int or not 1 <= intervals <= self.max_coupled_intervals:
            raise ValueError('budget_coupled_intervals')
        self.check_trace_reservation(intervals)

    def check_catchment(self, cells, intervals=72):
        if cells > self.max_bucket_cells or cells * intervals > self.max_bucket_entries:
            raise ValueError('budget_rainfall_entries')
        if cells * intervals * 8 > self.max_local_q_bytes:
            raise ValueError('budget_local_q_bytes')

    def check_trace_reservation(self, intervals):
        # Each existing water and sediment solve has a 128 MiB trace cap. Reserving
        # both complete caps per interval is intentionally conservative, not a
        # prediction of actual adaptive step counts or compressed archive size.
        from terrain_pipeline.surface_hydraulics import MAX_TRACE_BYTES
        from terrain_pipeline.surface_rivers.metric_sediment import MAX_BYTES
        reserved = intervals * (MAX_TRACE_BYTES + MAX_BYTES)
        if reserved > self.max_trace_reserved_bytes:
            raise ValueError('budget_trace_reservation')
        return reserved

    def check_nodes(self, nodes):
        if nodes > self.max_channel_nodes:
            raise ValueError('budget_channel_nodes')


def current_rss_bytes():
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
                 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
        value = Counters()
        value.cb = ctypes.sizeof(value)
        process = ctypes.windll.kernel32.GetCurrentProcess
        process.restype = ctypes.c_void_p
        if not ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(process()), ctypes.byref(value), value.cb):
            raise OSError('current working set unavailable')
        return int(value.WorkingSetSize)
    status = Path('/proc/self/status')
    if status.is_file():
        with status.open('r', encoding='ascii') as stream:
            for line in stream:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1]) * 1024
    raise OSError('current RSS unavailable on this platform; not substituted with lifetime peak')


_ACTIVE = ContextVar('native_river_resource_observer', default=None)
DEFAULT_BUDGET = ComputeBudget()


def active_budget():
    observer = _ACTIVE.get()
    return observer.budget if observer is not None else DEFAULT_BUDGET


class StageObserver:
    """Sampling is not an OS memory quota; phase boundaries are also sampled."""
    def __init__(self, budget, *, period_seconds=.02, on_limit=None):
        budget.validate()
        if not math.isfinite(period_seconds) or period_seconds <= 0:
            raise ValueError('invalid sample period')
        self.budget = budget
        self.period = period_seconds
        self.on_limit = on_limit
        self.stages = {}
        self.failure = None
        self._stage = None
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def _sample(self):
        rss = current_rss_bytes()
        elapsed = time.perf_counter() - self._start
        with self._lock:
            if self._stage is not None:
                stats = self.stages[self._stage]
                stats['max_sampled_current_rss_bytes'] = max(stats['max_sampled_current_rss_bytes'], rss)
                stats['samples'] += 1
            if self.failure is None:
                if rss > self.budget.max_rss_bytes:
                    self.failure = {'reason': 'budget_rss', 'observed_bytes': rss}
                elif elapsed > self.budget.max_seconds:
                    self.failure = {'reason': 'budget_seconds', 'observed_seconds': elapsed}
            failure = self.failure
        if failure is not None and self.on_limit is not None:
            self.on_limit(failure)

    def _loop(self):
        while not self._stop.wait(self.period):
            try:
                self._sample()
            except Exception as exc:
                self.failure = {'reason': 'resource_measurement_failed', 'error': str(exc)}
                if self.on_limit is not None:
                    self.on_limit(self.failure)
                return

    def check(self):
        if self.failure is not None:
            raise ValueError(self.failure['reason'])

    def __enter__(self):
        self._start = time.perf_counter()
        self._sample()
        self.check()
        self._token = _ACTIVE.set(self)
        self._thread = threading.Thread(target=self._loop, name='native-river-rss', daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join()
        _ACTIVE.reset(self._token)
        if exc[0] is None:
            self.check()

    @contextmanager
    def stage(self, name):
        self.check()
        with self._lock:
            if self._stage is not None or name in self.stages:
                raise ValueError('resource stages must be unique and non-nested')
            self.stages[name] = {'wall_seconds': 0.0, 'max_sampled_current_rss_bytes': 0, 'samples': 0}
            self._stage = name
        start = time.perf_counter()
        try:
            self._sample()
            self.check()
            yield
        finally:
            self._sample()
            with self._lock:
                self.stages[name]['wall_seconds'] = time.perf_counter()-start
                self._stage = None
        self.check()

    def record(self):
        return {'method': 'current process RSS sampled within each stage and at both boundaries',
                'sample_period_seconds': self.period, 'sampling_can_miss_between_sample_spikes': True,
                'is_os_memory_quota': False, 'budget': asdict(self.budget),
                'stages': self.stages, 'failure': self.failure}


def observed_call(name, function, *args, **kwargs):
    observer = _ACTIVE.get()
    if observer is None:
        return function(*args, **kwargs)
    with observer.stage(name):
        return function(*args, **kwargs)
