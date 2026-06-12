"""LLM backends — same tool-calling agent loop over two providers, as stateful sessions.

  ollama:  local Qwen3 via Ollama (default; private, no API cost).
  claude:  Claude API (Anthropic SDK) — for comparison and as a fallback.

A session holds the conversation history, so multi-turn chat (follow-ups that refer
back) works. Both adapt the provider-neutral tool registry from tools.py, run the
agentic loop (model -> tool calls -> results -> repeat), and return a uniform dict.
"""

DEFAULT_OLLAMA_MODEL = "qwen3:30b"
# CLAUDE.md designates claude-sonnet as the API fallback (~$0.006/query). Override
# with --model on the CLI if you want Opus.
DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"

MAX_STEPS = 8  # tool-call rounds per user turn before we bail


def _result(backend, model, answer, tool_calls):
    return {"backend": backend, "model": model, "answer": (answer or "").strip(),
            "tool_calls": tool_calls}


class OllamaSession:
    """Multi-turn chat against a local Ollama model via its REST API.

    Uses stdlib urllib rather than the `ollama` package: the package's httpx client
    honors the Windows system proxy and fails to reach the local server. Honors
    OLLAMA_HOST (normalizing a scheme-less / 0.0.0.0 value to a loopback URL).
    """

    def __init__(self, system, tools, dispatch, model=DEFAULT_OLLAMA_MODEL, keep_alive="15m"):
        import os
        raw = os.environ.get("OLLAMA_HOST") or "127.0.0.1:11434"
        if "://" not in raw:
            raw = "http://" + raw
        self._url = raw.replace("0.0.0.0", "127.0.0.1").rstrip("/") + "/api/chat"
        # Keep the model resident between turns so interactive chat is snappy. We do NOT
        # read the global OLLAMA_KEEP_ALIVE here: it's often set to 0 server-wide to free
        # VRAM, which would unload the model after every turn. Per-request keep_alive
        # overrides that. Pass keep_alive='-1' to never unload, '0' to unload immediately.
        self._keep_alive = keep_alive
        self.model = model
        self.dispatch = dispatch
        self._tools = [{"type": "function", "function": {
            "name": t["name"], "description": t["description"], "parameters": t["parameters"]}}
            for t in tools]
        self.messages = [{"role": "system", "content": system}]

    def _post(self, body):
        import json
        import urllib.request
        req = urllib.request.Request(
            self._url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())

    def send(self, user):
        self.messages.append({"role": "user", "content": user})
        calls = []
        for _ in range(MAX_STEPS):
            resp = self._post({"model": self.model, "messages": self.messages,
                               "tools": self._tools, "stream": False,
                               "keep_alive": self._keep_alive})
            msg = resp["message"]
            self.messages.append(msg)
            tcs = msg.get("tool_calls") or []
            if not tcs:
                return _result("ollama", self.model, msg.get("content", ""), calls)
            for tc in tcs:
                name = tc["function"]["name"]
                args = tc["function"].get("arguments") or {}
                out = self.dispatch(name, args)
                calls.append((name, dict(args), out))
                self.messages.append({"role": "tool", "tool_name": name, "content": out})
        return _result("ollama", self.model, "(stopped: max tool-call rounds reached)", calls)


def _resolve_claude_key():
    """Find an API key WITHOUT colliding with ANTHROPIC_API_KEY.

    IMPORTANT: don't read ANTHROPIC_API_KEY by default — Claude Code (and other agents)
    use that same var and exporting it switches THEIR billing to pay-per-use. So this tool
    uses a dedicated SC2TC_ANTHROPIC_API_KEY, or a gitignored key file, instead. Only falls
    back to ANTHROPIC_API_KEY if you explicitly opt in via SC2TC_USE_ANTHROPIC_API_KEY=1.
    """
    import os
    from pathlib import Path
    key = os.environ.get("SC2TC_ANTHROPIC_API_KEY")
    if key:
        return key.strip()
    for p in (Path(__file__).resolve().parents[3] / ".anthropic_key",
              Path.home() / ".config" / "sc2tc" / "anthropic_key"):
        if p.exists():
            return p.read_text().strip()
    if os.environ.get("SC2TC_USE_ANTHROPIC_API_KEY") == "1":
        return os.environ.get("ANTHROPIC_API_KEY")
    return None


class ClaudeSession:
    """Multi-turn chat against the Claude API. Needs a key via SC2TC_ANTHROPIC_API_KEY
    or a .anthropic_key file (NOT the shared ANTHROPIC_API_KEY — that bills Claude Code)."""

    def __init__(self, system, tools, dispatch, model=DEFAULT_CLAUDE_MODEL):
        import anthropic
        key = _resolve_claude_key()
        if not key:
            raise RuntimeError(
                "No SC2 API key. Set SC2TC_ANTHROPIC_API_KEY=sk-ant-... (do NOT use "
                "ANTHROPIC_API_KEY — Claude Code bills against that), or put the key in "
                "a '.anthropic_key' file in the repo root.")
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model
        self.system = system
        self.dispatch = dispatch
        self._tools = [{"name": t["name"], "description": t["description"],
                        "input_schema": t["parameters"]} for t in tools]
        self.messages = []

    def send(self, user):
        self.messages.append({"role": "user", "content": user})
        calls = []
        for _ in range(MAX_STEPS):
            resp = self._client.messages.create(
                model=self.model, max_tokens=2048, system=self.system,
                tools=self._tools, messages=self.messages)
            if resp.stop_reason != "tool_use":
                answer = "".join(b.text for b in resp.content if b.type == "text")
                self.messages.append({"role": "assistant", "content": resp.content})
                return _result("claude", self.model, answer, calls)
            self.messages.append({"role": "assistant", "content": resp.content})
            results = []
            for b in resp.content:
                if b.type == "tool_use":
                    out = self.dispatch(b.name, b.input)
                    calls.append((b.name, dict(b.input), out))
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
            self.messages.append({"role": "user", "content": results})
        return _result("claude", self.model, "(stopped: max tool-call rounds reached)", calls)


SESSIONS = {"ollama": OllamaSession, "claude": ClaudeSession}


# One-shot wrappers (stateless) — used by agent.ask() and tests.
def run_ollama(system, user, tools, dispatch, model=DEFAULT_OLLAMA_MODEL):
    return OllamaSession(system, tools, dispatch, model).send(user)


def run_claude(system, user, tools, dispatch, model=DEFAULT_CLAUDE_MODEL):
    return ClaudeSession(system, tools, dispatch, model).send(user)


BACKENDS = {"ollama": run_ollama, "claude": run_claude}
