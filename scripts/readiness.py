"""Bounded readiness polling shared by local smoke checks."""
import math
import os
import subprocess
import time
import urllib.error


def wait_for(label, probe):
    timeout = float(os.environ.get("SMOKE_READY_TIMEOUT", "120"))
    if timeout <= 0 or not math.isfinite(timeout):
        raise ValueError("SMOKE_READY_TIMEOUT must be a finite positive number")
    deadline = time.monotonic() + timeout
    print(f"Waiting for {label} (up to {timeout:g}s)...", flush=True)
    last_error = "probe did not succeed"
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"{label} not ready after {timeout:g}s: {last_error}")
        try:
            result = probe(min(5, remaining))
            if result is False:
                raise AssertionError("probe returned false")
            print(f"READY {label}", flush=True)
            return result
        except (OSError, urllib.error.URLError, subprocess.SubprocessError,
                AssertionError, ValueError) as exc:
            last_error = str(exc)
            stderr = getattr(exc, "stderr", None)
            if stderr:
                last_error += ": " + (stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr).strip()
        time.sleep(min(1, max(0, deadline - time.monotonic())))
