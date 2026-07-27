import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DiskStatus:
    free_gb: float
    warning: bool
    blocked: bool


class DiskSpaceGuard:
    def __init__(self, warn_gb: float = 15.0, minimum_gb: float = 10.0, path: str = "."):
        self.warn_gb = warn_gb
        self.minimum_gb = minimum_gb
        self.path = Path(path)

    def check(self) -> DiskStatus:
        free = shutil.disk_usage(str(self.path)).free / (1024 ** 3)
        return DiskStatus(round(free, 3), free < self.warn_gb, free < self.minimum_gb)

    def enforce(self, large_task: bool, auto_calculate_features: bool) -> DiskStatus:
        status = self.check()
        if status.blocked and large_task and auto_calculate_features:
            raise RuntimeError("磁盘剩余空间不足，已禁止大范围Feature补算。")
        return status
