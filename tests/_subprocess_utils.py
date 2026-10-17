"""Helpers for subprocess tests that need a bounded address space."""

from pathlib import Path
import subprocess
import sys
import textwrap


def linux_address_space_limit_available():
    """Return whether this process can measure and cap Linux virtual memory."""
    if sys.platform != "linux" or not Path("/proc/self/status").is_file():
        return False
    try:
        import resource
    except ImportError:
        return False
    return hasattr(resource, "RLIMIT_AS")


def run_address_space_limited(
    script,
    *,
    prepare="",
    memory_headroom=64 * 1024 * 1024,
    timeout=30,
    disable_core=False,
):
    """Run Python code after setup, with RLIMIT_AS capped relative to setup."""
    if not linux_address_space_limit_available():
        raise RuntimeError("Linux /proc status and resource.RLIMIT_AS are required")

    source = "import resource\nfrom pathlib import Path\n\n"
    if prepare:
        source += textwrap.dedent(prepare).strip() + "\n\n"
    source += textwrap.dedent(
        f"""
        baseline = int(next(
            line for line in Path('/proc/self/status').read_text().splitlines()
            if line.startswith('VmSize:')
        ).split()[1]) * 1024
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        ceiling = baseline + {int(memory_headroom)}
        if hard != resource.RLIM_INFINITY:
            ceiling = min(ceiling, hard)
        """
    )
    if disable_core:
        source += "resource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n"
    source += "resource.setrlimit(resource.RLIMIT_AS, (ceiling, hard))\n\n"
    source += textwrap.dedent(script).strip() + "\n"
    return subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
