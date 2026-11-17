from unittest.mock import patch

from app.services.rag_retrieve import format_rag_block
from app.services.script_expand import ScriptExpandService


class _FakeLLM:
    def __init__(self):
        self.messages = None

    def chat(self, messages):
        self.messages = messages
        return (
            '{"scenes":[{"name":"A","location":"L","time":"夜","characters":["S"],'
            '"props":[],"description":"d","dialogue_count":0,"narration_count":0,'
            '"lines":['
            '{"type":"dialogue","speaker":"S","text":"你好","emotion":"平静"},'
            '{"type":"dialogue","speaker":"S","text":"快走","emotion":"急切"},'
            '{"type":"dialogue","speaker":"S","text":"到了","emotion":"平静"}]}]}',
            "fake",
        )


def test_expand_includes_rag_block_when_retrieve_returns():
    llm = _FakeLLM()
    svc = ScriptExpandService(llm=llm)
    with patch(
        "app.services.rag_retrieve.build_rag_context",
        return_value=format_rag_block(
            [{"case": {"title": "参考甲", "description": "描述", "prompt_en": "p"}}]
        ),
    ):
        scenes = svc.expand(text="一句话创意", style="玄幻")
    assert scenes
    user = llm.messages[1]["content"]
    assert "参考案例" in user
    assert "参考甲" in user
