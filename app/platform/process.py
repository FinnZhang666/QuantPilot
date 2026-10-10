"""Small cross-platform process helpers used by runtime launchers."""

import ctypes
import os


def process_exists(pid: int) -> bool:
    """Return whether *pid* currently exists without sending a real signal."""
    if pid <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            process_query_limited_information, False, pid,
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        # Access denied means the process exists but is owned by a context that
        # cannot be queried by this user.
        return ctypes.get_last_error() == 5
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True
