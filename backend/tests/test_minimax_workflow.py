from app.services.workflows.minimax import (
    DEFAULT_HEIGHT,
    DEFAULT_LENGTH,
    DEFAULT_WIDTH,
    UNET_NAME,
    build_minimax_workflow,
)


def test_t2v_contains_core_nodes_and_prompt():
    wf = build_minimax_workflow("a rainy dock at night", mode="t2v", seed=1)
    types = {n["class_type"] for n in wf.values()}
    assert "MiniMaxH3ImageToVideo" in types
    assert "SamplerCustomAdvanced" in types
    assert "SaveVideo" in types
    assert "LoadImage" not in types
    assert UNET_NAME in str(wf)
    i2v = next(n for n in wf.values() if n["class_type"] == "MiniMaxH3ImageToVideo")
    assert i2v["inputs"]["prompt"] == "a rainy dock at night"
    assert i2v["inputs"]["width"] == DEFAULT_WIDTH
    assert i2v["inputs"]["height"] == DEFAULT_HEIGHT
    assert i2v["inputs"]["length"] == DEFAULT_LENGTH


def test_i2v_requires_and_wires_first_frame():
    wf = build_minimax_workflow(
        "push in",
        mode="i2v",
        first_frame_name="frame.png",
        seed=2,
    )
    types = {n["class_type"] for n in wf.values()}
    assert "LoadImage" in types
    load = next(n for n in wf.values() if n["class_type"] == "LoadImage")
    assert load["inputs"]["image"] == "frame.png"
    i2v = next(n for n in wf.values() if n["class_type"] == "MiniMaxH3ImageToVideo")
    assert "first_frame" in i2v["inputs"]


def test_empty_prompt_raises():
    import pytest

    with pytest.raises(ValueError, match="prompt"):
        build_minimax_workflow("  ")
