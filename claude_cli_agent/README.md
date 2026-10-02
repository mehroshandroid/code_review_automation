# claude_cli_agent

A small FastAPI service that runs natively on your machine (never in
Docker) so the review pipeline can use your own locally authenticated
`claude` CLI session as an LLM provider -- the same session you already
use interactively (e.g. in VS Code). Nothing beyond your normal Claude
usage is billed: this never uses an API key or `--bare` mode, which would
bypass your logged-in session entirely.

It's started the same way Ollama and `mac_build_agent` already are:
manually, outside `docker-compose`, and the backend container reaches it
over `host.docker.internal`.

## Prerequisites

- The `claude` CLI installed and already logged in (`claude login`) --
  if you can run `claude` interactively today, you're set.
- Python 3.

## Setup (one-time)

```bash
cd claude_cli_agent
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

## Running it

```bash
cd claude_cli_agent
venv/bin/uvicorn main:app --host 0.0.0.0 --port 8200
```

Leave this running in its own terminal tab while you use the app. The
backend container is already configured (via `CLAUDE_CLI_AGENT_URL` in
`docker-compose.yml`) to reach it at `http://host.docker.internal:8200` --
no other setup needed on the backend side.

To confirm it's up:

```bash
curl http://localhost:8200/health
# {"status":"ok"}
```

## What happens if it's not running

Nothing breaks. Selecting "Claude CLI (local)" as the provider still
completes the review -- each category just gets a placeholder score with
a remark explaining the agent wasn't reachable, the same way Azure OpenAI
degrades to stub mode when no key is configured.

## Endpoints

- `GET /health` -- liveness check.
- `POST /ask` -- takes `{"prompt": "<text>"}`, runs `claude` non
  -interactively against it, and returns `{"status": "ok", "result":
  "<text>"}` or `{"status": "error", "message": "<why>"}`.

## Safety: what each invocation can and can't do

Every call runs as:

```
claude --print --output-format json --max-turns 1 --restricted --permission-prompts none "<prompt>"
```

from a **freshly created, empty temporary directory** that's deleted
immediately afterward. `--restricted` strips out Bash/code-execution
tools and WebFetch, and confines any remaining file tools to that working
directory -- so even though this runs unsandboxed on your real
filesystem (not inside Docker), there's nothing there for it to read, and
nothing it writes outlives the request. `--permission-prompts none`
denies anything that would otherwise need an answer, so a call can never
hang waiting for a human who isn't present.

## Cost and latency, in practice

Even a one-word answer costs real money and takes a few seconds, because
Claude Code loads its default tool/system-prompt context before
answering at all -- this isn't optional overhead you can configure away,
it's inherent to invoking the CLI rather than a bare chat-completions
API. A full review scores several categories plus a general-remarks pass,
so expect this provider to be noticeably slower and more expensive per
review than Azure OpenAI or local Ollama. Pick it when you specifically
want Claude's judgment on a review, not as a default.
