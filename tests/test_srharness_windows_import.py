# tests/test_srharness_windows_import.py
import platform

import pytest
pytest.importorskip('sr_harness', reason='optional SRHarness bridge environment required')

pytestmark = pytest.mark.skipif(
    platform.system() == "Linux",
    reason="Windows-only import compatibility checks",
)


def test_import_sr_harness_on_windows():
    import sr_harness  # noqa: F401


def test_landlock_functions_raise_on_non_linux():
    from sr_harness.runtime import landlock

    with pytest.raises(landlock.LandlockUnavailableError):
        landlock.landlock_abi()

    with pytest.raises(landlock.LandlockUnavailableError):
        landlock._syscall(0)

    with pytest.raises(landlock.LandlockUnavailableError):
        landlock.restrict_system_calls()


def test_get_sandbox_runner_raises_on_non_linux():
    from sr_harness.runtime.sandbox import SandboxUnavailableError, get_sandbox_runner

    with pytest.raises(SandboxUnavailableError):
        get_sandbox_runner()
