from app.services.h3_guide import GUIDE_COMMIT, load_base_guide, load_ref_guide


def test_official_h3_guides_are_loaded_from_vendored_resources():
    assert GUIDE_COMMIT == "d21241f0a4b3acbb34c97dae47fa417b7065e438"
    assert "integrated_multimodal_description" in load_base_guide()
    assert "subject_definitions" in load_ref_guide()


def test_base_guide_contains_exact_i2va_alignment_instruction():
    assert (
        "For the target video, at 0.00 seconds into the target video, "
        "<Picture 1> (from [Shot 1]) is fully referenced."
    ) in load_base_guide()
