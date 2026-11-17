# ============================================
# LLM 输出的健壮 JSON 解析
# ============================================
# 本地小模型输出偶发：结尾带散文、尾逗号、截断
# 统一在此恢复，供 script_expand / breakdown / polish 共用
# ============================================

from __future__ import annotations

import json
import re
from typing import Any


def _strip_fence(raw: str) -> str:
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    # 丢开头非 JSON 的散文，定位到 { 或 [
    first = min(
        (i for i in (raw.find("{"), raw.find("[")) if i != -1),
        default=-1,
    )
    if first > 0:
        raw = raw[first:]
    return raw.strip()


def _loads_obj(text: str) -> dict[str, Any]:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise json.JSONDecodeError("root must be object", text, 0)
    return data


def _escape_unescaped_quotes(text: str) -> str:
    """Escape quotes that LLM left raw inside JSON string values.

    A valid opening quote is preceded by a JSON structure char ([{,: or start);
    a valid closing quote is followed by one (,}]: or end/whitespace). Any other
    quote is treated as content inside a string and escaped, e.g.
    "他说"快跑"" -> "他说\"快跑\"".
    """
    out: list[str] = []
    n = len(text)
    in_str = False
    i = 0
    while i < n:
        ch = text[i]
        if ch == "\\" and in_str:
            out.append(ch)
            if i + 1 < n:
                out.append(text[i + 1])
                i += 1
            i += 1
            continue
        if ch != '"':
            out.append(ch)
            i += 1
            continue
        if not in_str:
            prev = text[i - 1] if i > 0 else ""
            if prev and prev not in "[{,: \t\n" and not prev.isspace():
                out.append('\\"')
            else:
                in_str = True
                out.append(ch)
        else:
            nxt = text[i + 1] if i + 1 < n else ""
            if nxt in ",}]:\t\n" or nxt == "":
                in_str = False
                out.append(ch)
            else:
                out.append('\\"')
        i += 1
    return "".join(out)


def parse_llm_json(raw: str) -> dict[str, Any]:
    """解析 LLM 输出 JSON 对象；失败抛出 json.JSONDecodeError。"""
    text = _strip_fence(raw)
    if not text:
        raise json.JSONDecodeError("empty llm output", raw, 0)

    try:
        return _loads_obj(text)
    except json.JSONDecodeError:
        pass

    # 修复尾逗号
    fixed = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        return _loads_obj(fixed)
    except json.JSONDecodeError:
        pass

    # 未转义直引号（LLM 常把台词直接写成 "..."）
    quoted = _escape_unescaped_quotes(text)
    if quoted != text:
        try:
            return _loads_obj(quoted)
        except json.JSONDecodeError:
            pass
        fixed_q = re.sub(r",\s*([}\]])", r"\1", quoted)
        try:
            return _loads_obj(fixed_q)
        except json.JSONDecodeError:
            pass

    # 截断恢复：给"打开未闭合的括号"补上闭合，丢掉未闭合字符串
    try:
        return _loads_obj(_balance_truncated(quoted))
    except json.JSONDecodeError:
        pass

    # JSONDecoder.raw_decode 吃掉第一个完整对象（尾部散文场景）
    try:
        obj, _ = json.JSONDecoder().raw_decode(fixed)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    raise json.JSONDecodeError(f"invalid llm json: {raw[:200]!r}", raw, 0)


def _balance_truncated(text: str) -> str:
    """为截断的 JSON 补闭合括号；未闭合字符串丢到最近一个补全点。

    先转义字符串值中的未转义直引号，避免内部引号干扰括号平衡判定。
    """
    text = _escape_unescaped_quotes(text)
    stack: list[str] = []
    in_str = False
    esc = False
    str_start = -1
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
                str_start = -1
            continue
        if ch == '"':
            in_str = True
            str_start = i
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()

    if in_str and str_start > 0:
        # 丢弃未闭合字符串
        cut = text.rfind(",", 0, str_start)
        text = text[: cut if cut > 0 else str_start]

    closers = ["]" if ch == "[" else "}" for ch in reversed(stack)]
    fixed = text.rstrip().rstrip(",").rstrip() + "".join(closers)
    if fixed.rstrip().endswith((":", ",")):
        fixed = fixed.rstrip() + '""'
    return fixed