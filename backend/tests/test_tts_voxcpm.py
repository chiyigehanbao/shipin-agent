from pathlib import Path

import pytest

from app.services.tts.voxcpm_provider import VoxCPMNotReady, VoxCPMProvider


def test_voxcpm_missing_dir(tmp_path: Path):
    p = VoxCPMProvider(model_dir=tmp_path / "nope")
    with pytest.raises(VoxCPMNotReady):
        p.synthesize(text="hi")
