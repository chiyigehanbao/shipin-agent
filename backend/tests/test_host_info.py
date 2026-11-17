from unittest.mock import MagicMock, patch

from app.services.host_info import read_host_stats


def test_read_host_stats_ok():
    with patch("app.services.host_info.psutil") as p:
        p.cpu_percent.return_value = 12.5
        p.virtual_memory.return_value.percent = 48.0
        p.disk_usage.return_value.percent = 35.0
        h = read_host_stats()
    assert h["cpu_percent"] == 12.5
    assert h["memory_percent"] == 48.0
    assert h["disk_percent"] == 35.0


def test_read_host_stats_failure_returns_nulls():
    with patch("app.services.host_info.psutil") as p:
        p.cpu_percent.side_effect = RuntimeError("x")
        h = read_host_stats()
    assert h["cpu_percent"] is None
    assert h["memory_percent"] is None
    assert h["disk_percent"] is None
