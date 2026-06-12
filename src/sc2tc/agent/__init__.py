"""Query/assistant layer — answer natural-language SC2 questions by calling the
verified calculators/DB as tools, never recalling stats from the model's weights.

Local-first: defaults to a local Qwen3 model via Ollama. A Claude API backend is
available for comparison and as a fallback (see CLAUDE.md tech-stack table).
"""
