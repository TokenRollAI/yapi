# Security Policy

## Supported versions

`yapi` (PyPI: `pyyapi`) is still in the 0.x line. Only the latest
minor release receives security fixes; older minors are not patched.

| Version | Supported |
|---|---|
| 0.2.x   | ✅        |
| < 0.2   | ❌        |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security-sensitive
reports. Use one of these private channels instead:

- **GitHub Security Advisory** (preferred): open a draft advisory at
  https://github.com/TokenRollAI/yapi/security/advisories/new
- **Email**: send a description and reproduction to
  `shuaiqijianhao@qq.com` with subject `[yapi-security] ...`.

You can expect:

- An acknowledgement within 7 days.
- A status update at least every 14 days while the issue is open.
- Coordinated disclosure once a fix is released — credit will be given
  in the GitHub Release notes unless you ask to stay anonymous.

## Scope

`yapi` is a thin layer over FastAPI + PydanticAI. Vulnerabilities in
those upstream libraries should be reported to the respective projects;
this policy covers issues specifically in the `yapi` source code,
default `PydanticAIRunner`, or release pipeline (Trusted Publishing
config, package contents, etc.).

Out of scope:

- Provider-side LLM behavior (prompt injection, hallucination, refusal
  bypasses). `yapi` does not implement guardrails; safety lives in the
  prompt and the application layer.
- Misconfiguration of the deploying application (exposed `OPENAI_API_KEY`,
  open CORS, missing auth). Standard FastAPI security practices apply.
