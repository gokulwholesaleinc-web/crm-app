# AI assistant disabled 2026-05-07 pending Claude API rebuild.
# The package-level re-export of `ai_router` was removed so importing
# anything from this package (e.g. `src.ai.embedding_hooks`) doesn't
# transitively pull in the OpenAI SDK + the full router graph at boot.
# Restore by uncommenting the line below:
# from src.ai.router import router as ai_router  # noqa: F401
