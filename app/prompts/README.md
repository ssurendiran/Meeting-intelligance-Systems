# Versioned prompts

Prompts are stored under **versioned directories** so you can change and version them without touching code.

## Layout

```
app/prompts/
  loader.py          # load_prompts(component, version), get_system_prompt(), get_user_prompt()
  v1/
    rag_answer.yaml      # RAG /ask and /ask_stream (system + user)
    rag_rewrite.yaml     # Query rewriter (system only)
    extract_summary.yaml # /summary (system + user)
  v2/                   # Future version: copy v1, edit, set PROMPT_VERSION=v2
    ...
```

## Version

- **Env:** `PROMPT_VERSION` (default: `v1`).
- **Config:** `settings.prompt_version` in `app/core/config.py`.

## Components

| Component         | Used by                    | Placeholders                    |
|------------------|----------------------------|---------------------------------|
| `rag_answer`     | answerer, streamer         | `<<ALLOWED_EVIDENCE>>`, `<<QUESTION>>`, `<<CONTEXT>>` |
| `rag_rewrite`    | query_rewriter            | (user message = raw question)   |
| `extract_summary`| summarizer                 | `<<ALLOWED_EVIDENCE>>`, `<<CONTEXT>>` |

## Adding a new version

1. Copy a version folder, e.g. `cp -r v1 v2`.
2. Edit YAML under `v2/` (e.g. `rag_answer.yaml`).
3. Set `PROMPT_VERSION=v2` (env or .env) to use it.

## YAML format

Each file can have:

- **version:** (optional) label, e.g. `v1`.
- **system:** (optional) system prompt text; use `|` for multiline.
- **user:** (optional) user prompt template; use `|` for multiline.

Example:

```yaml
version: v1
system: |
  You are a Meeting Intelligence Assistant.
  ...
user: |
  Question: <<QUESTION>>
  Context: <<CONTEXT>>
```
