# discord-net

A research/testing harness that connects **accounts you own** to Discord and
coordinates them across a server. Accounts converse naturally **about Learnora**
(a study platform), answer real users' questions, and run scripted/scheduled
activity. Traffic is paced to look human: max 6 messages/min, randomized
40-45s breaks, typing delays, and long replies split into chunks.

> **Important**: Only use this with accounts you own. Running automated account
> activity may violate Discord's Terms of Service even for your own accounts.
> Use a burner/test server and keep activity modest and human-like. You are
> responsible for how this tool is used.

## Features

- **Learnora context** — accounts know the product (from learnora.ai) and use
  it as the topic of conversation. They start threads, share opinions, and
  answer questions about it accurately.
- **OpenCode Zen LLM** — natural Discord-style replies generated via
  `https://opencode.ai/zen/v1` (`/chat/completions`). Short, casual, no AI
  formatting (no em dashes, no lists, no "as an AI..."). Configurable model.
- **Per-account memory** — each account keeps its own rolling conversation
  history so it reacts to what it personally saw/said.
- **Answers real users** — replies to direct questions and mentions, plus a
  probabilistic casual response otherwise.
- **Human imperfections** — replies are LLM-generated fresh each time, then a
  naturalizer randomly adds lowercase starts, dropped apostrophes, and famous
  chat abbreviations (`plz`, `tbh`, `idk`, `tho`, `cuz`, `ngl`, ...).
- **Human pacing**:
  - Max **6 messages per minute** per account (configurable).
  - Randomized **40-45s quiet breaks**.
  - **Typing simulation** — waits a realistic per-word time before sending.
  - Replies over ~180 chars are **split into multiple messages**.
  - Gateway logins are **staggered** between accounts.
- **Auto-join & channel analysis** — accounts that aren't in the target server
  join it via a configured `invite_code` (with organic delays), then fetch and
  track all text channels; new channels are picked up live.
- **Scripted scheduler** — optional configured actions (messages, reactions,
  presence) on natural randomized cadence.
- **Gateway + REST** — full WebSocket gateway per account for live events,
  REST for sending.

## Requirements

- Python 3.10+
- Own Discord user access token(s)
- OpenCode Zen API key (optional but recommended; otherwise a local fallback
  is used and replies will be much less natural)

## Quick start

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

1. Edit `config.json`:
   - Set each account's user token in `accounts[i].token`.
   - Set `llm.api_key` to your OpenCode Zen key (or put it in `.env` as
     `LLM_API_KEY`).
   - Set `chat.server_id` to the server id.
   - (Optional) `chat.invite_code` - a Discord invite code or link. If an
     account is **not** already a member of `chat.server_id`, it will join via
     this invite automatically (with human-like delays).
   - Set `chat.channel_ids` to the channels to watch/act in. Leave empty to
     auto-detect all text channels of the server.
2. Run:

```bash
python run.py
```

Press `Ctrl+C` to stop.

## Auto-join & channel analysis

On startup and every `chat.recheck_interval` seconds, each account:

1. Checks whether it's a member of `chat.server_id` (`GET /users/@me/guilds`).
2. If it isn't, and `chat.invite_code` is set, it waits a random 20-45s, then
   joins via the invite (spaced out across accounts to look natural).
3. Fetches **all text channels** (`GET /guilds/{server_id}/channels`) and
   records them as watch channels when `channel_ids` is empty.
4. Keeps the set fresh: new channels created later are added automatically via
   gateway events; if the account leaves/is removed, it re-checks and re-joins.

## Configuration (`config.json`)

| Section | Key | Meaning |
|---|---|---|
| `accounts` | `token` | Your owned account's Discord user token. |
| | `name` / `personality` | Label + persona used to steer LLM replies. |
| | `response_chance` | Chance an account replies to a non-question message. |
| | `min/max_reply_delay` | Random seconds before replying. |
| `chat` | `server_id`, `channel_ids` | Where accounts operate. |
| | `invite_code` | Discord invite (code or full link) used to auto-join. |
| | `recheck_interval` | Seconds between membership/channel re-checks (default 900). |
| | `respond_to_users` | Reply to real user messages. |
| | `chat_with_bots` | Also reply to other bots. |
| `llm` | `enabled`, `base_url`, `api_key`, `model` | OpenCode Zen config. Model examples: `deepseek-v4-flash`, `big-pickle`, `kimi-k2.6`. |
| `rate_limit` | `max_per_minute` | Per-account ceiling (default 6). |
| | `min_gap_between_messages` | Seconds between sends. |
| | `break_min` / `break_max` | Quiet break length range (default 40-45s). |
| | `break_chance` | Chance of starting a break. |
| `typing` | `enabled`, `min/max_seconds` | Typing simulation bounds. |
| `scripted` | `enabled`, `actions` | Optional scheduled actions. |

### Scripted actions

```jsonc
{
  "enabled": true,
  "actions": [
    { "account_index": 0, "channel_id": 123, "kind": "message",
      "content": "Good morning everyone!", "delay_before": 10.0 },
    { "account_index": 1, "channel_id": 123, "kind": "reaction", "emoji": "👍" }
  ]
}
```

Action `kind` values: `message` | `reaction` | `presence`.

## Project layout

```
discord_net/
├── core/
│   ├── api.py              # Discord REST + OpenCode Zen LLM client
│   ├── config.py           # config.json parsing/validation
│   ├── gateway.py          # WebSocket gateway lifecycle
│   ├── heartbeat.py        # heartbeat keep-alive
│   ├── ratelimit.py        # per-account 6/min + break enforcement
│   ├── splitter.py         # message chunking
│   ├── typing.py           # typing delay simulation
│   └── learnora_context.py # Learnora knowledge base for the LLM
├── engines/
│   ├── agent.py            # one account: gateway, memory, replies
│   ├── conversation.py     # fleet manager + chatter/thread loops
│   └── generator.py        # LLM wrapper + local fallback + humanize()
└── scheduler/
    └── scripted.py         # scheduled actions
```

## Notes / safety

- **Credentials**: `config.json`, `.env`, and everything ending in `*.env`
  are git-ignored. Never commit real tokens or API keys.
- **Self-botting**: Using a real user token for automation violates Discord's
  ToS. Keep this to a private test server and keep behavior modest.
- **Rate limits**: The built-in limiter keeps you under Discord's thresholds;
  don't lower the gaps.

## License

MIT (customize as needed).