import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("discord_net.config")

DEFAULT_CONFIG_PATH = Path("config.json")

ZEN_BASE_URL = "https://opencode.ai/zen/v1"
ZEN_DEFAULT_MODEL = "deepseek-v4-flash"


@dataclass
class AccountConfig:
    name: str = ""
    personality: str = ""
    token: str = ""
    response_chance: float = 0.5
    min_reply_delay: float = 3.0
    max_reply_delay: float = 15.0
    profile: str = "student"
    email: str = ""
    password: str = ""


@dataclass
class ChatConfig:
    server_id: int = 0
    channel_ids: List[int] = field(default_factory=list)
    invite_code: str = ""
    recheck_interval: int = 900
    respond_to_users: bool = True
    chat_with_bots: bool = True


@dataclass
class LlmConfig:
    enabled: bool = True
    base_url: str = ZEN_BASE_URL
    api_key: str = ""
    model: str = ZEN_DEFAULT_MODEL
    temperature: float = 0.9
    max_tokens: int = 120


@dataclass
class RateLimitConfig:
    max_per_minute: int = 6
    min_gap_between_messages: float = 8.0
    break_min: float = 40.0
    break_max: float = 45.0
    break_chance: float = 0.35


@dataclass
class TypingConfig:
    enabled: bool = True
    min_seconds: float = 1.5
    max_seconds: float = 15.0


@dataclass
class ScriptedAction:
    account_index: int = 0
    channel_id: int = 0
    kind: str = "message"  # message | reaction | presence
    content: str = ""
    emoji: str = ""
    delay_before: float = 0.0


@dataclass
class ScriptedConfig:
    enabled: bool = False
    actions: List[ScriptedAction] = field(default_factory=list)


@dataclass
class Config:
    accounts: List[AccountConfig]
    chat: ChatConfig
    llm: LlmConfig = field(default_factory=LlmConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    typing: TypingConfig = field(default_factory=TypingConfig)
    scripted: ScriptedConfig = field(default_factory=ScriptedConfig)
    gateway_url: str = "wss://gateway.discord.gg/?v=9&encoding=json"
    api_url: str = "https://discord.com/api/v9"
    intents: int = 327679
    max_message_len: int = 180
    use_browser: bool = False

    @classmethod
    def from_file(
        cls, path: Path = DEFAULT_CONFIG_PATH, create_template: bool = True
    ) -> "Config":
        path = Path(path)
        if not path.exists():
            if create_template:
                log.warning("Config %s missing; writing template", path)
                path.write_text(TEMPLATE_JSON, encoding="utf-8")
            else:
                raise FileNotFoundError(f"Config file not found: {path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        merged = {**DEFAULT_CONFIG, **data}

        accounts = []
        for acc in merged.get("accounts", []):
            accounts.append(
                AccountConfig(
                    name=acc.get("name", ""),
                    personality=acc.get("personality", ""),
                    token=acc.get("token", ""),
                    response_chance=float(acc.get("response_chance", 0.5)),
                    min_reply_delay=float(acc.get("min_reply_delay", 3.0)),
                    max_reply_delay=float(acc.get("max_reply_delay", 15.0)),
                    profile=acc.get("profile", "student"),
                    email=acc.get("email", ""),
                    password=acc.get("password", ""),
                )
            )

        chat_data = merged.get("chat", {})
        chat = ChatConfig(
            server_id=int(chat_data.get("server_id", 0)),
            channel_ids=[int(c) for c in chat_data.get("channel_ids", [])],
            invite_code=chat_data.get("invite_code", ""),
            recheck_interval=int(chat_data.get("recheck_interval", 900)),
            respond_to_users=bool(chat_data.get("respond_to_users", True)),
            chat_with_bots=bool(chat_data.get("chat_with_bots", True)),
        )

        llm_data = merged.get("llm", {})
        llm = LlmConfig(
            enabled=bool(llm_data.get("enabled", True)),
            base_url=llm_data.get("base_url", ZEN_BASE_URL),
            api_key=llm_data.get("api_key", ""),
            model=llm_data.get("model", ZEN_DEFAULT_MODEL),
            temperature=float(llm_data.get("temperature", 0.9)),
            max_tokens=int(llm_data.get("max_tokens", 120)),
        )

        rl_data = merged.get("rate_limit", {})
        rate_limit = RateLimitConfig(
            max_per_minute=int(rl_data.get("max_per_minute", 6)),
            min_gap_between_messages=float(rl_data.get("min_gap_between_messages", 8.0)),
            break_min=float(rl_data.get("break_min", 40.0)),
            break_max=float(rl_data.get("break_max", 45.0)),
            break_chance=float(rl_data.get("break_chance", 0.35)),
        )

        ty_data = merged.get("typing", {})
        typing = TypingConfig(
            enabled=bool(ty_data.get("enabled", True)),
            min_seconds=float(ty_data.get("min_seconds", 1.5)),
            max_seconds=float(ty_data.get("max_seconds", 15.0)),
        )

        scripted_data = merged.get("scripted", {})
        actions = []
        for a in scripted_data.get("actions", []):
            actions.append(
                ScriptedAction(
                    account_index=int(a.get("account_index", 0)),
                    channel_id=int(a.get("channel_id", 0)),
                    kind=a.get("kind", "message"),
                    content=a.get("content", ""),
                    emoji=a.get("emoji", ""),
                    delay_before=float(a.get("delay_before", 0.0)),
                )
            )
        scripted = ScriptedConfig(
            enabled=bool(scripted_data.get("enabled", False)),
            actions=actions,
        )

        return cls(
            accounts=accounts,
            chat=chat,
            llm=llm,
            rate_limit=rate_limit,
            typing=typing,
            scripted=scripted,
            gateway_url=merged.get(
                "gateway_url", "wss://gateway.discord.gg/?v=9&encoding=json"
            ),
            api_url=merged.get("api_url", "https://discord.com/api/v9"),
            intents=int(merged.get("intents", 327679)),
            max_message_len=int(merged.get("max_message_len", 180)),
            use_browser=bool(merged.get("use_browser", False)),
        )

    def validate(self) -> List[str]:
        errors = []
        if not self.accounts:
            errors.append("No accounts configured in config.json")
        for i, a in enumerate(self.accounts):
            if not a.token:
                errors.append(f"Account {i} ('{a.name}') has an empty token")
        env_key = os.getenv("LLM_API_KEY", "")
        if self.llm.enabled and not real_key(self.llm.api_key) and not real_key(env_key):
            errors.append(
                "LLM enabled but no real key (set llm.api_key in config.json or "
                "LLM_API_KEY in .env)"
            )
        if self.chat.server_id == 0:
            errors.append("chat.server_id must be set to your server id")
        return errors


def real_key(value: str) -> bool:
    """True if a value looks like an actual key, not a placeholder."""
    if not value:
        return False
    v = value.strip().lower()
    return "replace" not in v and "your" not in v and "token" not in v


DEFAULT_CONFIG: Dict[str, Any] = {
    "accounts": [],
    "chat": {"server_id": 0, "channel_ids": [], "invite_code": "", "recheck_interval": 900, "respond_to_users": True, "chat_with_bots": True},
    "llm": {"enabled": True, "base_url": ZEN_BASE_URL, "api_key": "", "model": ZEN_DEFAULT_MODEL, "temperature": 0.9, "max_tokens": 120},
    "rate_limit": {"max_per_minute": 6, "min_gap_between_messages": 8.0, "break_min": 40.0, "break_max": 45.0, "break_chance": 0.35},
    "typing": {"enabled": True, "min_seconds": 1.5, "max_seconds": 15.0},
    "scripted": {"enabled": False, "actions": []},
    "gateway_url": "wss://gateway.discord.gg/?v=9&encoding=json",
    "api_url": "https://discord.com/api/v9",
    "intents": 327679,
    "max_message_len": 180,
}

TEMPLATE_JSON = json.dumps(
    {
        "accounts": [
            {
                "name": "Account1",
                "personality": "college freshman studying computer science, upbeat, casual, types in short bursts",
                "token": "YOUR_ACCOUNT_TOKEN_1",
                "response_chance": 0.5,
                "min_reply_delay": 3.0,
                "max_reply_delay": 15.0,
                "profile": "student",
            },
            {
                "name": "Account2",
                "personality": "high school senior prepping for SATs, laid back, friendly",
                "token": "YOUR_ACCOUNT_TOKEN_2",
                "response_chance": 0.5,
                "min_reply_delay": 3.0,
                "max_reply_delay": 15.0,
                "profile": "student",
            },
        ],
        "chat": {
            "server_id": 0,
            "channel_ids": [],
            "invite_code": "",
            "recheck_interval": 900,
            "respond_to_users": True,
            "chat_with_bots": True,
        },
        "llm": {
            "enabled": True,
            "base_url": ZEN_BASE_URL,
            "api_key": "",
            "model": ZEN_DEFAULT_MODEL,
            "temperature": 0.9,
            "max_tokens": 120,
        },
        "rate_limit": {
            "max_per_minute": 6,
            "min_gap_between_messages": 8.0,
            "break_min": 40.0,
            "break_max": 45.0,
            "break_chance": 0.35,
        },
        "typing": {"enabled": True, "min_seconds": 1.5, "max_seconds": 15.0},
        "scripted": {"enabled": False, "actions": []},
        "gateway_url": "wss://gateway.discord.gg/?v=9&encoding=json",
        "api_url": "https://discord.com/api/v9",
        "intents": 327679,
        "max_message_len": 180,
    },
    indent=2,
)