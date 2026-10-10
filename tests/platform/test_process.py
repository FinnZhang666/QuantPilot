import os

from app.platform.process import process_exists


def test_process_exists_for_current_process():
    assert process_exists(os.getpid()) is True


def test_process_exists_rejects_invalid_pid():
    assert process_exists(0) is False
    assert process_exists(-1) is False
