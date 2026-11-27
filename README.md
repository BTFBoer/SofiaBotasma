# Sofia — a private Telegram companion

A private Telegram chat with **Sofia**: a fictional 32-year-old woman with her own personality, life, opinions, moods and boundaries, who remembers you, changes slowly as you get to know each other, and texts like a person rather than an assistant.

One user. Local SQLite memory. Long polling by default. Built on python-telegram-bot 22 and the OpenAI Responses API, behind a provider abstraction.

> 🇳🇱 **Nog nooit geprogrammeerd? Begin bij [HANDLEIDING.md](HANDLEIDING.md)** — stap voor stap, met een startbestand waar je op dubbelklikt (`START-WINDOWS.bat`, of `start.sh` op een Mac) en een installatie-assistent die je codes controleert en je Telegram-ID zelf vindt.

> **This repository is public.** The intimate parts of the persona live in git-ignored `*.private.yaml` overlay files (see [Private overlays](#private-overlays)). Never commit `.env`, `data/` or `persona/*.private.yaml`. If you want everything in git, make the repository private first.

---

## Contents

- [What it does](#what-it-does)
- [How it works](#how-it-works)
- [Project structure](#project-structure)
- [Setup sequence](#setup-sequence)
- [Running it](#running-it) — macOS/Linux · Windows · VPS/containers
- [Commands](#commands)
- [Customizing Sofia](#customizing-sofia)
- [Models and cost](#models-and-cost)
- [Privacy and data](#privacy-and-data)
- [Webhooks instead of polling](#webhooks-instead-of-polling)
- [Tests](#tests)
- [Troubleshooting](#troubleshooting)
- [BotFather configuration](#botfather-configuration)

---

## What it does

- **Texts like a person.** 1–4 bubbles per reply, sent one by one with Telegram's real typing indicator and human-ish timing (≈1–8 s, a bit longer for heavy replies; model latency counts towards it). Mostly short; long when it matters. Questions are optional. Occasionally just an emoji reaction.
- **Reads your burst, answers once.** Messages sent in quick succession are batched (debounce). If you add something while she's "typing", she re-reads everything before sending.
- **Remembers in layers** (SQLite):
  - recent chat, verbatim (token-budgeted, ~40 messages);
  - long-term memories about you (content, category, importance, confidence, created/last-referenced dates, source message id, optional event date), de-duplicated and periodically consolidated;
  - episodic summaries of older conversations ("the late-night talk about Lisbon");
  - Sofia's own established facts, so her claims stay true ("she hates raisins" can't flip next week);
  - relationship memory: inside jokes, pet names, boundaries, shared themes;
  - open threads: things left hanging that would naturally come back.
- **Retrieves, doesn't dump.** Each turn selects relevant memories (embeddings + lexical overlap + importance + recency), always includes boundaries/pet names, and surfaces dated events automatically as they approach.
- **Has a relationship model.** Familiarity, trust, affection, attraction, playfulness, emotional openness, sexual comfort, irritation, mood, current dynamic. The model only ever sees qualitative descriptions, never numbers. Change is slow by construction (small per-turn nudges, diminishing returns, daily caps); irritation and mood decay over hours, not after one message.
- **Keeps things latent.** Her biography is tagged by reveal level (open → familiar → trusted → deep), gated by closeness. Private dynamics are staged (latent → emerging → established) and only enter the prompt when *you* raise them.
- **Optional initiative.** `/proactive on` lets her occasionally text first — at most twice a day, usually not at all, never in quiet hours, never twice in a row without a reply, always grown from real continuity, never needy.
- **Sees photos, hears voice notes** (transcription), understands replies/quotes, stickers, forwards (treated as untrusted content).
- **Honest when asked.** In conversation she stays in character. Asked sincerely whether she's an AI, she says so. She never claims a body as fact, never agrees to meet, never pretends to see you.
- **Private by default.** Allowlist of one Telegram user id; group chats ignored; strangers get silence. Out-of-character controls for memory, export, reset, privacy.

## How it works

```
Telegram update
  └─ gate: allowlist · private chat only · de-duplicate update ids
      └─ handler: text / photo / voice / sticker / reply / forward → IncomingMessage → SQLite
          └─ coordinator: debounce burst → one batch per turn, per-chat lock
              └─ engine.plan_reply
                  1. recent messages (verbatim, token budget)
                  2. relevant memories (+ boundaries, pet names, near events)
                  3. open threads
                  4. mood + relationship state (time decay applied)
                  5. time since last interaction, what she's plausibly doing now
                  6. generate (strict JSON) → validate → recover / regenerate once
              └─ send bubbles with typing + timing, record each with its Telegram id
              └─ engine.apply: relationship nudges, mood, memories, Sofia facts, threads
              └─ background: episode summaries, consolidation, expiry
```

**Context sent to the model** (in this order):

| Part | Where | Notes |
|---|---|---|
| System prompt + Sofia persona + Bram profile | `instructions` | Static and byte-identical every call → provider prompt caching |
| Current state: time/date, gap, mood, relationship (qualitative), sharing level | developer message | Never numbers |
| Open threads, selected memories, Sofia's established facts, earlier moments | developer message | Only what's relevant |
| Private dynamics guidance (only once emerging) + style check | developer message | e.g. "your last 4 replies ended with a question" |
| Recent chat, verbatim, with time-gap markers | user / assistant items | Each bubble is its own item |
| Your current message(s) (+ images, reply context) | user items | |
| Final reminder | developer message | |

**Structured output.** The model returns JSON validated against a strict schema: `messages`, `reaction`, `image_note`, `mood_update`, `relationship_update` (nudges −2…+2), `dynamic_note`, `established_dynamics`, `memory_candidates`, `sofia_facts`, `unresolved_threads`, `used_memory_ids`. Only `messages` (and an optional emoji reaction) ever reach Telegram. Bad output is recovered (code fences, chatter around JSON, truncated JSON, plain text) or regenerated once; drafts that slip into assistant voice ("How can I help?") are rewritten once.

**Why the Responses API without server-side conversation state.** Calls are stateless with `store=false`. The local database is the single source of truth and the context is re-assembled from memory every turn, so `previous_response_id` / the Conversations API would only duplicate intimate data on the provider's side. (The Assistants API is not used.)

**Failures.** Transient API errors are retried with exponential backoff. If the model is still unavailable Sofia sends a neutral "wait, something glitched on my side 🙃 try that again?" (excluded from future context). If the provider refuses a message, you get a short out-of-character notice instead of an in-character "no" that would misrepresent her. Stack traces only go to the local log.

## Project structure

```
app/
  __main__.py             python -m app
  main.py                 entry point, --check, --init-db
  config.py               environment configuration
  telegram_bot.py         gate, handlers, media, delivery, commands, jobs
  controls.py             out-of-character logic: memory/forget/export/reset/privacy
  healthcheck.py          container health check (heartbeat file)
  llm/
    provider.py           provider interface, retries, factory
    openai_provider.py    OpenAI Responses API (default)
    openai_compat_provider.py  any OpenAI-compatible Chat Completions endpoint
  companion/
    engine.py             one turn: context → generate → validate → apply
    prompts.py            system prompt, context assembly, summary/consolidation prompts
    persona.py            persona/profile loading with private overlays
    state.py              relationship & mood model
    dynamics.py           staged private dynamics
    schemas.py            JSON schemas, pydantic models, parsing & recovery
    style.py              bubble cleanup, Telegram splitting, style feedback
    coordinator.py        per-chat debounce / batching
  memory/
    schema.sql            database schema
    database.py           async SQLite layer (aiosqlite)
    models.py             row objects
    store.py              data access
    retrieval.py          memory selection
    extraction.py         memory filtering, de-duplication, consolidation
    episodes.py           episodic summarization
    text.py               normalization, similarity, embeddings packing
  scheduler/
    proactive.py          spontaneous messages
  utils/
    logging.py timing.py timeutil.py
persona/
  persona.yaml                         Sofia: static core, voice, biography, tastes, routine, initial state
  user_profile.yaml                    Bram: stable starting profile (writer background)
  user_profile.private.example.yaml    format of the private overlay
  persona.private.yaml                 (git-ignored) your private additions to Sofia
  user_profile.private.yaml            (git-ignored) your private profile & staged dynamics
deploy/sofia.service    systemd unit
tests/                  pytest suite
Dockerfile  docker-compose.yml  requirements.txt  requirements-dev.txt  pyproject.toml  .env.example
```

## Setup sequence

Beginner route: double-click `START-WINDOWS.bat` (Windows) or run `bash start.sh` (macOS/Linux). The script finds Python 3.12–3.14, creates `.venv`, installs requirements, runs the interactive setup (`python -m app --setup`: validates the token and key live, finds your Telegram id, picks a model your key can use, writes `.env`) and starts the bot. Re-run setup with `INSTELLEN-WINDOWS.bat` or `bash start.sh --setup`. Python 3.15 is refused for now: the pinned pydantic-core and PyYAML have no 3.15 wheels yet.

Manual route:

1. **Create the bot.** In Telegram, open **@BotFather**, send `/newbot`, display name `Sofia`, and a username ending in `bot` (see [BotFather configuration](#botfather-configuration) for the rest).
2. **Get the token.** BotFather replies with a token like `123456789:AA…`. Keep it secret.
3. **Get your numeric Telegram user id.** Easiest: leave `ALLOWED_TELEGRAM_USER_ID` empty, start the bot (step 6) and send it anything — in setup mode it replies *only* with your id. (Alternative: message **@userinfobot**.) Put the id in `.env` and restart.
4. **Create `.env`.** `cp .env.example .env` (Windows: `copy .env.example .env`) and set `TELEGRAM_BOT_TOKEN` and `ALLOWED_TELEGRAM_USER_ID`.
5. **Add the LLM key.** Set `OPENAI_API_KEY` and choose `LLM_MODEL` (see [Models and cost](#models-and-cost)). Place your private overlays in `persona/` if you have them.
6. **Install and run.** See [Running it](#running-it). Check first: `python -m app --check`.
7. **Send `/start`.** You get one out-of-character line, then Sofia opens the chat herself.
8. **Verify persistent memory.** Tell her something durable ("I'm going to Levenslang on 23 October, Mulero is closing"). Run `/memory` — it should be listed. Restart the bot, run `/memory` again: still there. Near the date, she'll bring it up on her own.
9. **Enable `/proactive on` only if you want her to text first sometimes.** It's off by default.

## Running it

Requires **Python 3.12+**.

### A. macOS / Linux

```bash
git clone https://github.com/<you>/<repo>.git sofia-telegram && cd sofia-telegram
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # then edit .env
# copy your private overlays into persona/ if you have them
python -m app --check           # validates config + persona files
python -m app                   # runs the bot (Ctrl+C to stop)
```

### B. Windows (PowerShell)

```powershell
git clone https://github.com/<you>/<repo>.git sofia-telegram; cd sofia-telegram
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r requirements.txt
copy .env.example .env            # then edit .env (Notepad is fine)
python -m app --check
python -m app
```

`tzdata` is included in the requirements because Windows has no system time-zone database.

### C. Continuously on a small VPS or container host

Any small Linux VPS (1 vCPU / 512 MB–1 GB RAM is plenty) or any host that runs a Docker container with a persistent volume. No inbound ports are needed for long polling.

**With Docker Compose (recommended)**

```bash
git clone https://github.com/<you>/<repo>.git sofia-telegram && cd sofia-telegram
cp .env.example .env && nano .env
# from your own machine: scp persona/*.private.yaml user@server:~/sofia-telegram/persona/
docker compose up -d --build
docker compose logs -f            # watch it come online
```

- Data lives in the named volume `sofia-data` and survives rebuilds.
- `persona/` is mounted read-only, so the private overlays are used without being baked into the image. After editing persona files: `docker compose restart`.
- Health: `docker compose ps` shows `healthy` once the heartbeat runs.
- Update: `git pull && docker compose up -d --build`.
- Backup: use `/export` in Telegram, or `docker compose stop && docker compose cp sofia:/app/data ./backup-data && docker compose start`.

**Without Docker (systemd)**

```bash
sudo useradd --system --create-home sofia
sudo mkdir -p /opt/sofia-telegram && sudo chown sofia: /opt/sofia-telegram
sudo -u sofia git clone https://github.com/<you>/<repo>.git /opt/sofia-telegram
cd /opt/sofia-telegram
sudo -u sofia python3.12 -m venv .venv
sudo -u sofia .venv/bin/pip install -r requirements.txt
sudo -u sofia cp .env.example .env && sudo -u sofia nano .env
sudo -u sofia mkdir -p data
sudo cp deploy/sofia.service /etc/systemd/system/sofia.service
sudo systemctl daemon-reload && sudo systemctl enable --now sofia
journalctl -u sofia -f
```

Run **one** instance per bot token. Two pollers on the same token fight over updates.

## Commands

Out-of-character controls. Sofia never sees them; they're never stored as conversation.

| Command | What it does |
|---|---|
| `/start` | First time: a one-line note, then Sofia opens the chat. Later: a reminder of `/help`. |
| `/memory` | Human-readable summary of what's remembered: about you, between you two, recent moments, open threads, counts. |
| `/forget <words>` | Finds matching memories/moments and asks which to delete (buttons). Deleted means deleted. The raw chat log keeps the original messages until `/reset`. |
| `/proactive on\|off` | Spontaneous messages. Without an argument: shows the current setting. |
| `/privacy` | Where data is stored and what is sent to the provider. |
| `/export` | Sends you a JSON file with everything: chat log, memories, episodes, threads, state, settings. |
| `/reset` | After confirmation (5 minutes), erases history, memories, episodes, threads and relationship state. Settings stay. |
| `/about` | What Sofia is, factually. |
| `/help` | Lists the commands. |

## Customizing Sofia

`persona/persona.yaml` is structured as:

- **`static_core`** — identity, temperament, values, contradictions, humor, attraction, boundaries, conflict/affection/support style. The app never writes to this file; conversation cannot overwrite her core.
- **`voice`** — how she texts (Dutch/English/Portuguese flavor, emoji habits, what she never does).
- **`biography`, `stories`** — her established life, tagged `open / familiar / trusted / deep`. The current sharing level follows closeness (familiarity + trust + openness); deeper material stays latent until then.
- **`tastes`, `quirks`, `routine`** — the routine's `schedule` drives "what she's plausibly doing right now" (studio at 11:00 on a Tuesday, should-be-asleep at 00:40).
- **`learned_character_facts`** — seeds. Facts she establishes in conversation go to the database automatically (older claims win when they conflict).
- **`initial_state`** — starting mood and relationship. The live state is in the database.

`persona/user_profile.yaml` is background for the *writer*: Sofia only "knows" what's under `known_to_sofia_from_start`, and learns everything else from you. Learned facts belong in the database, not here.

### Private overlays

Any `X.private.yaml` next to `X.yaml` is deep-merged over it at startup (dicts merge, lists append, scalars replace) and is git-ignored. Use them for anything intimate.

`user_profile.private.yaml` can define `intimate_profile`:

- `general` — always visible to the writer: what intimacy means to you, dynamics you enjoy, things to avoid.
- `dynamics` — **staged** elements. Each has `detect_keywords`, `emerging_guidance`, `established_guidance`, `sofia_side` and `min_days_between_sofia_initiations`.
  - **latent**: nothing in the prompt. Sofia doesn't know.
  - **emerging**: one of the keywords appeared in a message from *you* (whole-word match, your messages only). The emerging guidance enters the context: she may notice, let it pass, or offer one deniable remark — but doesn't name it.
  - **established**: the model marks it once it's genuinely out in the open between you. Full guidance plus recency: when you last touched it and when she last brought it up herself. If she initiated it within the cooldown, she's told to leave it alone unless you raise it — so it never turns her into a caricature.

See `persona/user_profile.private.example.yaml` for the format. `python -m app --check` lists the dynamics it found.

## Models and cost

- `LLM_MODEL` is required and never hard-coded. The model must support **image input** (for photos) and **Structured Outputs**. The example in `.env.example` (`gpt-6.1-sol`, utility `gpt-6-luna`) comes from the model list in the current OpenAI Python SDK; check OpenAI's model page for current availability, pricing and behaviour before you settle.
- Reasoning models: keep `LLM_REASONING_EFFORT=low` (or `minimal`/`none` if supported) — high effort makes texting feel slow. If your model rejects the parameter, leave it empty. `LLM_MAX_OUTPUT_TOKENS` includes reasoning tokens.
- Per reply, roughly: ~7–9k static tokens (system prompt + persona + profile, cached by the provider after the first call) + 1–4k dynamic tokens + a few hundred output tokens. Plus one small embedding call. Background summaries/consolidation run on `UTILITY_MODEL` every few dozen messages.
- Using another provider: set `LLM_PROVIDER=openai_compatible`, `LLM_BASE_URL=…`, `OPENAI_API_KEY=<that provider's key>`, and if the endpoint lacks strict JSON-schema support, `LLM_JSON_MODE=json_object`. Embeddings/transcription use the same endpoint; leave those models empty if it doesn't offer them.
- **Adult content** is governed by the provider you use and its current policies — the companion doesn't try to work around them. If a request is refused you'll see a short out-of-character notice.

## Privacy and data

- **Local:** everything lives in `DATABASE_PATH` (SQLite): chat log, memories, episodes, threads, relationship state, settings. Photos and voice notes are processed in memory and not stored (unless `KEEP_IMAGES=true`); only a short text note of a photo may be kept. Logs contain metadata, not message contents, unless `LOG_LEVEL=DEBUG`.
- **Sent to the LLM provider per reply:** instructions, persona and profile (including private overlays), selected memories and summaries, the recent chat verbatim, your message, photos/voice audio when you send them, and memory/message snippets for embeddings. Sent with `store=false`; the provider's own retention policy still applies.
- **Telegram:** bot chats are cloud chats, not end-to-end encrypted.
- **Controls:** `/memory`, `/forget`, `/export`, `/reset`. Deleting `data/` (or the Docker volume) removes everything.
- **Access:** only `ALLOWED_TELEGRAM_USER_ID` is served. Others are ignored before anything is stored or sent anywhere. Disable group joining in BotFather (below).

## Webhooks instead of polling

Polling needs no open ports and is the right default for a personal bot. For webhooks: `pip install "python-telegram-bot[job-queue,webhooks]==22.8"`, put the bot behind HTTPS (reverse proxy), and set:

```
TELEGRAM_MODE=webhook
WEBHOOK_URL=https://your.domain/sofia
WEBHOOK_LISTEN=0.0.0.0
WEBHOOK_PORT=8443
WEBHOOK_SECRET=<random string>
```

The webhook path is derived from a hash of the token. Nothing else changes.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Covers: unauthorized users blocked (gate and handlers), memory storage/de-duplication/deletion, persistence across restarts, context retrieval (relevance, near events, always-on items, embeddings), structured output parsing and recovery, schema strictness, `/reset` and `/forget` confirmation flows and export, Telegram message splitting and bubble cleanup, human timing bounds, relationship state dynamics, proactive rules, batching, the full delivery path with a fake Telegram bot, provider retry/backoff, and failure recovery (outages, garbage output, refusals, assistant-voice rewrites). The test for staged private dynamics runs only when a private overlay is present.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Bot replies "Setup mode. Your Telegram user ID is …" | Put that id in `ALLOWED_TELEGRAM_USER_ID` and restart. |
| No reply at all | Check logs. `ignored update from unauthorized user` → wrong id. Make sure only one instance runs. |
| Every reply is the "glitched" message | The LLM call fails: look for the error in the logs. Common: wrong model name, `LLM_REASONING_EFFORT`/`LLM_TEMPERATURE` not supported by that model, invalid key, no credit. |
| "The model provider declined…" | The provider refused that message. Rephrase, or use a provider whose policy fits. |
| Photos ignored | `VISION_ENABLED=true` and a model with image input. |
| Voice notes not understood | Set `TRANSCRIPTION_MODEL`. |
| She feels too slow | Lower `LLM_REASONING_EFFORT`, use a faster model, lower `DEBOUNCE_SECONDS`. |
| `--check` shows `private dynamics: none` | The `*.private.yaml` overlays aren't in `PERSONA_DIR` (or, in Docker, not in the mounted `./persona`). |

---

## BotFather configuration

In Telegram, open **@BotFather**:

1. Send `/newbot`.
2. Bot display name: **`Sofia`**
3. Choose an available username ending in `bot` (e.g. `sofia_<something>_bot`). It doesn't need to be findable; nobody else can talk to it anyway.
4. Copy the token BotFather sends into `TELEGRAM_BOT_TOKEN` in `.env`.
5. `/setdescription` → choose the bot → paste **BOT DESCRIPTION** below (shown on the empty chat screen before `/start`; max 512 characters).
6. `/setabouttext` → choose the bot → paste **BOT ABOUT TEXT** below (profile page; max 120 characters).
7. `/setuserpic` → choose the bot → send a square image. Suggestion that fits her: a detail from a public-domain old painting (a hand, a draped sleeve, a still-life corner — the Rijksmuseum's public-domain collection is a good source). Avoid photos of real people.
8. `/setcommands` → choose the bot → paste **BOT COMMAND LIST** below. (The bot also sets these itself on startup.)
9. `/setjoingroups` → choose the bot → **Disable**. Optionally `/setprivacy` → **Enable** (group privacy mode).

**BOT DESCRIPTION**

```
Private chat.

Sofia — 32, Rotterdam. Restores old paintings for a living, stays up too late, has opinions about almost everything and changes her mind about almost none of them.

A fictional character, here for one person only.
```

**BOT ABOUT TEXT**

```
Sofia. Fictional, private, and slightly opinionated.
```

**BOT COMMAND LIST**

```
start - Start Sofia
memory - View remembered information
forget - Remove a memory
proactive - Control spontaneous messages
privacy - Data and privacy information
export - Export your data
reset - Reset Sofia's memory
about - About Sofia
help - List commands
```
