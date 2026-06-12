"""CLI for the SC2 theorycrafting assistant.

    python -m sc2tc.agent.cli "does +1 zealot two-shot a zergling?"
    python -m sc2tc.agent.cli "when can I afford gate and core with 8 workers?" --backend claude
    python -m sc2tc.agent.cli "how many marines to kill a roach?" --compare
    python -m sc2tc.agent.cli "..." --show-tools     # also print which tools were called
    python -m sc2tc.agent.cli -i                     # interactive chat (keeps context)

Local Ollama is the default backend (needs `ollama serve` + the model pulled).
The claude backend needs a key in SC2TC_ANTHROPIC_API_KEY or a .anthropic_key file —
NOT the shared ANTHROPIC_API_KEY (Claude Code bills against that one).
"""

import argparse
import sys

from .agent import ask, compare, start_session, route

# Models emit Unicode (arrows, dashes); the default Windows console is cp1252 and
# would crash on them. Print UTF-8, replacing anything unencodable.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def repl(backend, model, show_tools, keep_alive="15m"):
    """Interactive chat loop — keeps conversation history so follow-ups work."""
    session = start_session(backend, model, keep_alive=keep_alive)
    print(f"SC2 5.0.16 assistant [{backend}:{session.model}] - type a question, "
          "'exit' to quit, 'reset' to clear context.")
    while True:
        try:
            q = input("sc2> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q.lower() in ("exit", "quit", ":q"):
            break
        if q.lower() == "reset":
            session = start_session(backend, model, keep_alive=keep_alive)
            print("(context cleared)")
            continue
        try:
            _print(session.send(q), show_tools)
        except Exception as e:
            print(f"error: {e}")


def _print(res, show_tools):
    tag = f"[{res.get('backend')}:{res.get('model')}]"
    if "error" in res:
        print(f"{tag} ERROR: {res['error']}")
        return
    if res.get("fallback_from"):
        print(f"(local backend failed, fell back to Claude: {res['fallback_from']})")
    if show_tools:
        for name, args, out in res.get("tool_calls", []):
            print(f"  - {name}({args}) -> {out.splitlines()[0][:100]}")
    print(f"{tag} {res['answer']}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Verified SC2 5.0.16 theorycrafting assistant.")
    p.add_argument("question", nargs="?", help="omit (or use -i) for interactive chat")
    p.add_argument("-i", "--interactive", action="store_true", help="interactive chat (keeps context)")
    p.add_argument("--backend", choices=["ollama", "claude", "auto"], default="ollama",
                   help="'auto' routes by difficulty: local for simple, Opus for ambiguous builds")
    p.add_argument("--model", help="override the backend's default model")
    p.add_argument("--compare", action="store_true", help="run both backends side by side")
    p.add_argument("--no-fallback", action="store_true", help="don't fall back to Claude")
    p.add_argument("--show-tools", action="store_true", help="print the tool calls made")
    p.add_argument("--keep-alive", default="15m",
                   help="ollama: how long to keep the model loaded ('15m', '-1'=never unload, '0'=off)")
    args = p.parse_args(argv)

    if args.interactive or args.question is None:
        repl(args.backend, args.model, args.show_tools, keep_alive=args.keep_alive)
        return

    if args.compare:
        for name, res in compare(args.question).items():
            _print(res, args.show_tools)
        return

    backend, model = args.backend, args.model
    if backend == "auto":
        backend, model, reason = route(args.question)
        print(f"[router] {reason} -> {backend}:{model or '(default)'}")
    _print(ask(args.question, backend=backend, model=model,
               fallback=not args.no_fallback), args.show_tools)


if __name__ == "__main__":
    main()
