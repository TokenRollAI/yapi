from yapi import PromptRouter


def test_public_exports_are_available() -> None:
    assert PromptRouter is not None
