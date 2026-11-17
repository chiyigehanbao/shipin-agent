from app.services.json_utils import parse_llm_json

import pytest


def test_plain():
    r = parse_llm_json('{"scenes": [{"name": "a"}]}')
    assert r["scenes"][0]["name"] == "a"


def test_fenced():
    r = parse_llm_json('```json\n{"a": 1}\n```')
    assert r["a"] == 1


def test_trailing_prose():
    r = parse_llm_json('{"a": 1}\n这里是补充说明，不是 JSON。')
    assert r["a"] == 1


def test_leading_prose():
    r = parse_llm_json('好的，以下是结果：\n{"a": 1}')
    assert r["a"] == 1


def test_trailing_comma():
    r = parse_llm_json('{"a": [1, 2,],}')
    assert r["a"] == [1, 2]


def test_truncated_object():
    r = parse_llm_json('{"scenes": [{"name": "a"}, {"name": "b"}')
    assert len(r["scenes"]) == 2


def test_root_not_object():
    with pytest.raises(Exception):
        parse_llm_json('[1, 2, 3]')


def test_invalid():
    with pytest.raises(Exception):
        parse_llm_json('not json at all')


def test_inner_unescaped_quotes():
    r = parse_llm_json('{"a": "他说\"快跑\"，然后转身"}')
    assert r["a"] == '他说"快跑"，然后转身'


def test_inner_quotes_and_truncated():
    raw = (
        '{"scenes":[{"name":"雨巷","description":"他大喊"快跑"，随即拔枪。远'
    )
    r = parse_llm_json(raw)
    assert "scenes" in r


def test_inner_quotes_in_lines_array():
    raw = (
        '{"scenes":[{"name":"A","lines":[{"type":"dialogue","speaker":"K",'
        '"text":"he said "hi" to him",'
    )
    r = parse_llm_json(raw)
    assert "scenes" in r