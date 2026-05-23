import pytest
from pydantic import BaseModel

from yapi.errors import RuntimeExecutionError
from yapi.prompt_context import PromptContext, _format_value


class SomeModel(BaseModel):
    name: str
    vip: bool


def test_add_str_passes_through():
    ctx = PromptContext()
    ctx.add("hello")
    assert ctx.segments() == ("hello",)


def test_add_basemodel_uses_model_dump_json():
    ctx = PromptContext()
    model = SomeModel(name="djj", vip=True)
    ctx.add(model)
    import json
    parsed = json.loads(ctx.segments()[0])
    assert parsed == {"name": "djj", "vip": True}


def test_add_dict_uses_json_dumps_with_ensure_ascii_false():
    ctx = PromptContext()
    ctx.add({"k": "中"})
    assert ctx.segments()[0] == '{"k": "中"}'


def test_add_list_uses_json_dumps():
    ctx = PromptContext()
    ctx.add([1, "中", True])
    assert ctx.segments()[0] == '[1, "中", true]'


def test_add_tuple_uses_json_dumps():
    ctx = PromptContext()
    ctx.add((1, 2))
    assert ctx.segments()[0] == "[1, 2]"


def test_add_other_uses_str():
    ctx = PromptContext()
    ctx.add(42)
    assert ctx.segments()[0] == "42"


def test_add_kv_format():
    ctx = PromptContext()
    ctx.add_kv("k", {"x": 1})
    assert ctx.segments()[0] == 'k: {"x": 1}'


def test_add_section_format():
    ctx = PromptContext()
    model = SomeModel(name="djj", vip=True)
    ctx.add_section("Profile", model)
    seg = ctx.segments()[0]
    assert seg.startswith("# Profile\n")
    import json
    body = seg[len("# Profile\n"):]
    parsed = json.loads(body)
    assert parsed == {"name": "djj", "vip": True}


def test_add_none_raises_runtime_error():
    ctx = PromptContext()
    with pytest.raises(RuntimeExecutionError):
        ctx.add(None)


def test_segments_returns_in_call_order():
    ctx = PromptContext()
    ctx.add("first")
    ctx.add_kv("key", "second")
    ctx.add_section("sec", "third")
    segs = ctx.segments()
    assert segs[0] == "first"
    assert segs[1] == "key: second"
    assert segs[2] == "# sec\nthird"


def test_empty_segments_returns_empty_tuple():
    ctx = PromptContext()
    assert ctx.segments() == ()
