from pathlib import Path


def test_python_39_baseline_is_declared():
    pyproject = Path("pyproject.toml").read_text()
    dockerfile = Path("Dockerfile").read_text()
    assert 'requires-python = ">=3.9,<3.10"' in pyproject
    assert "FROM python:3.9-slim" in dockerfile
    assert "python:3.12" not in dockerfile
