from app.services.gpu_info import parse_nvidia_smi_csv, read_gpu_stats

SAMPLE = "NVIDIA GeForce RTX 4070, 62, 78, 4200, 12282\n"


def test_parse_nvidia_smi_csv():
    g = parse_nvidia_smi_csv(SAMPLE)
    assert g["available"] is True
    assert g["temperature_c"] == 62
    assert g["utilization_percent"] == 78
    assert g["name"].startswith("NVIDIA")


def test_parse_empty_unavailable():
    g = parse_nvidia_smi_csv("")
    assert g["available"] is False
    assert g["temperature_c"] is None


def test_read_gpu_stats_uses_runner(monkeypatch):
    monkeypatch.setattr("app.services.gpu_info._run_nvidia_smi", lambda: SAMPLE)
    g = read_gpu_stats()
    assert g["available"] is True
    assert g["temperature_c"] == 62
