#!/usr/bin/env python3
import os
import signal
import subprocess
from pathlib import Path

PID_PATH = Path(__file__).resolve().parents[1] / "data" / "realtime.pid"
EXPECTED = "scripts/start_realtime.py"


def main() -> int:
    if not PID_PATH.exists():
        print("未找到实时行情服务PID文件，服务可能未运行。")
        return 0
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
    except ValueError:
        PID_PATH.unlink()
        print("PID文件无效，已安全清理。")
        return 0
    try:
        command = subprocess.check_output(["ps", "-p", str(pid), "-o", "command="], text=True).strip()
    except subprocess.CalledProcessError:
        PID_PATH.unlink()
        print("PID对应进程不存在，已清理无效PID文件。")
        return 0
    project = str(Path(__file__).resolve().parents[1])
    if EXPECTED not in command or project not in command:
        print("PID不属于当前项目实时行情进程，拒绝停止。")
        return 1
    os.kill(pid, signal.SIGTERM)
    print("已向当前项目实时行情服务发送安全停止请求，PID：%s" % pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

