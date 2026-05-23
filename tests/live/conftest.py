"""Live test gating.

Live tests hit a real LLM provider via PydanticAI. They are **skipped by default**
to keep the regular `uv run pytest` invocation offline, fast, and deterministic.

Enable them with:

    set -a; source .env; set +a
    uv run pytest tests/live --run-live -v

Two gates apply (both must pass):

1. `--run-live` CLI flag is set.
2. `YAPI_MODEL` env var is set to a real provider string (anything other than
   the empty string or the literal "test").

Provider credentials (e.g. `OPENAI_API_KEY`, `OPENAI_BASE_URL`) are consumed by
PydanticAI itself — yapi does not read them. See README "Configuration" section.
"""

import os

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="run live tests that hit a real LLM provider via PydanticAI",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: mark test as requiring a real LLM provider (skipped without --run-live)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    run_live = config.getoption("--run-live")
    yapi_model = os.getenv("YAPI_MODEL", "")
    real_provider = bool(yapi_model) and yapi_model != "test"

    skip_no_flag = pytest.mark.skip(
        reason="live tests skipped; pass --run-live to enable"
    )
    skip_no_model = pytest.mark.skip(
        reason="YAPI_MODEL not set to a real provider; live tests require provider creds"
    )

    for item in items:
        if "live" not in item.keywords:
            continue
        if not run_live:
            item.add_marker(skip_no_flag)
        elif not real_provider:
            item.add_marker(skip_no_model)
