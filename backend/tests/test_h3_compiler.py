from app.db.repositories.compiled_prompts import CompiledPromptRepository
from app.services.h3_compiler import H3PromptCompiler, canonical_source_hash
from app.services.h3_validator import I2VA_ALIGNMENT
from app.services.prompt_ir import H3SourceContext
from app.services.visual_bible import default_visual_bible


VALID_I2VA = f"""{I2VA_ALIGNMENT}

integrated_multimodal_description: [Shot 1] Live-action, cinematic, the woman shown in <Picture 1> preserves her appearance, clothing, position, and the room layout. The camera pushes in with small amplitude at slow speed as she lifts her gaze and says: <d>[Chinese] 别回头。</d>

overall_soundscape: Rain ticks against the window while fabric rustles softly.

non_diegetic_music: N/A"""


class FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return self.responses.pop(0), "ollama"


def context():
    return H3SourceContext(
        mode="i2va",
        duration_sec=5.17,
        project={"name": "雨巷", "style": "cinematic realism"},
        visual_bible=default_visual_bible(),
        subjects=[{"name": "苏晚", "identity": "polished young actor"}],
        scene={"name": "小吃摊", "time": "night"},
        shot={"movement": "slow push in", "image_url": "/media/f1.png"},
        dialogue=[{"speaker": "苏晚", "text": "别回头。", "type": "dialogue"}],
        soundscape="rain",
        music="none",
    )


def test_source_hash_is_canonical():
    first = context()
    second = H3SourceContext.model_validate(first.model_dump())
    assert canonical_source_hash(first) == canonical_source_hash(second)


def test_compiler_persists_valid_first_output(tmp_path):
    llm = FakeLLM(VALID_I2VA)
    repo = CompiledPromptRepository(tmp_path / "compiled.db")
    compiler = H3PromptCompiler(llm=llm, compiled_repo=repo)
    result = compiler.compile_context(
        project_id="p1", source_type="frame", source_id="f1", context=context()
    )
    assert result["validation_json"]["valid"] is True
    assert result["provider"] == "ollama"
    assert result["content"] == VALID_I2VA
    assert len(llm.calls) == 1


def test_compiler_repairs_invalid_output_once(tmp_path):
    llm = FakeLLM("not an H3 prompt", VALID_I2VA)
    compiler = H3PromptCompiler(
        llm=llm,
        compiled_repo=CompiledPromptRepository(tmp_path / "compiled.db"),
    )
    result = compiler.compile_context(
        project_id="p1", source_type="frame", source_id="f1", context=context()
    )
    assert result["validation_json"]["valid"] is True
    assert len(llm.calls) == 2
    assert "field_order" in str(llm.calls[1])


def test_compiler_persists_invalid_second_output_for_diagnosis(tmp_path):
    llm = FakeLLM("bad first", "bad second")
    compiler = H3PromptCompiler(
        llm=llm,
        compiled_repo=CompiledPromptRepository(tmp_path / "compiled.db"),
    )
    result = compiler.compile_context(
        project_id="p1", source_type="frame", source_id="f1", context=context()
    )
    assert result["validation_json"]["valid"] is False
    assert result["content"] == "bad second"
    assert len(llm.calls) == 2
