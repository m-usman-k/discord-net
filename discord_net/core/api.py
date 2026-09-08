import base64
import json
import logging
import random
import time
import uuid
from typing import Any, Dict, List, Optional

import aiohttp

log = logging.getLogger("discord_net.api")


class DiscordAPI:
    """Minimal Discord REST client using a user (OAuth) access token.

    Intended for accounts the operator owns and controls.
    """

    def __init__(
        self,
        token: str,
        api_url: str = "https://discord.com/api/v9",
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self.token = token
        self.api_url = api_url.rstrip("/")
        self._owns_session = session is None
        self._session = session
        # Generate unique per-instance values for headers
        self._installation_id = f"{random.randint(10**18, 10**19 - 1)}.{uuid.uuid4().hex[:20]}"
        self._launch_id = str(uuid.uuid4())
        self._session_id = uuid.uuid4().hex
        self._build_number = random.randint(600000, 699999)
        self._browser_version = f"{random.randint(130, 155)}.0.{random.randint(0, 9999)}.{random.randint(0, 999)}"

    def _super_properties(self) -> str:
        props = {
            "os": "Windows",
            "browser": "Chrome",
            "device": "",
            "system_locale": "en-GB",
            "has_client_mods": False,
            "browser_user_agent": (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{self._browser_version} Safari/537.36"
            ),
            "browser_version": self._browser_version,
            "os_version": "10",
            "referrer": "",
            "referring_domain": "",
            "referrer_current": "",
            "referring_domain_current": "",
            "release_channel": "stable",
            "client_build_number": self._build_number,
            "client_event_source": None,
            "client_launch_id": self._launch_id,
            "client_heartbeat_session_id": self._session_id,
            "client_app_state": "focused",
        }
        return base64.b64encode(json.dumps(props).encode()).decode()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    def _headers(self, channel_id: Optional[int] = None) -> Dict[str, str]:
        chrome_major = self._browser_version.split(".")[0]
        return {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "User-Agent": (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{self._browser_version} Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "DNT": "1",
            "Origin": "https://discord.com",
            "Referer": f"https://discord.com/channels/@me/{channel_id}" if channel_id else "https://discord.com/channels/@me",
            "Sec-Ch-Ua": f'"Chromium";v="{chrome_major}", "Not?A_Brand";v="24", "Google Chrome";v="{chrome_major}"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-Context-Properties": base64.b64encode(json.dumps({"location": "chat_input"}).encode()).decode(),
            "X-Debug-Options": "bugReporterEnabled",
            "X-Discord-Locale": "en-US",
            "X-Discord-Timezone": "Asia/Karachi",
            "X-Installation-Id": self._installation_id,
            "X-Super-Properties": self._super_properties(),
        }

    async def _request(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None, channel_id: Optional[int] = None,
    ) -> Any:
        session = await self._ensure_session()
        url = f"{self.api_url}{path}"
        kwargs: Dict[str, Any] = {"headers": self._headers(channel_id), "json": payload, "params": params}
        async with session.request(method, url, **kwargs) as resp:
            text = await resp.text()
            if resp.status >= 400:
                log.warning("API %s %s -> %s: %s", method, path, resp.status, text[:200])
                raise DiscordAPIError(f"{resp.status}: {text}", resp.status)
            if not text:
                return {}
            try:
                return await resp.json()
            except Exception:
                return text

    async def get_me(self) -> Dict[str, Any]:
        return await self._request("GET", "/users/@me")

    async def get_guilds(self) -> List[Dict[str, Any]]:
        data = await self._request("GET", "/users/@me/guilds")
        return data if isinstance(data, list) else []

    async def get_channels(self, guild_id: int) -> List[Dict[str, Any]]:
        data = await self._request("GET", f"/guilds/{guild_id}/channels")
        return data if isinstance(data, list) else []

    def _clean_invite(self, invite_code: str) -> str:
        code = (invite_code or "").strip().rstrip("/")
        if not code:
            return ""
        if "/" in code:
            code = code.split("/")[-1]
        return code

    async def join_server(self, invite_code: str) -> bool:
        code = self._clean_invite(invite_code)
        if not code:
            log.warning("No usable invite code to join")
            return False
        try:
            await self._request("POST", f"/invites/{code}", {})
            log.info("Joined server via invite %s", code)
            return True
        except DiscordAPIError as e:
            log.warning("Join via invite %s failed: %s", code, e)
            return False

    async def send_message(self, channel_id: int, content: str) -> Dict[str, Any]:
        nonce = str(random.randint(10**17, 10**18 - 1))
        return await self._request(
            "POST", f"/channels/{channel_id}/messages",
            {"content": content, "nonce": nonce, "mobile_push": False},
            channel_id=channel_id,
        )

    async def send_typing(self, channel_id: int) -> bool:
        try:
            await self._request("POST", f"/channels/{channel_id}/typing", channel_id=channel_id)
            return True
        except DiscordAPIError:
            return False

    async def react(self, channel_id: int, message_id: int, emoji: str) -> bool:
        import urllib.parse
        encoded = urllib.parse.quote(emoji, safe="")
        try:
            await self._request(
                "PUT",
                f"/channels/{channel_id}/messages/{message_id}/reactions/{encoded}",
                channel_id=channel_id,
            )
            return True
        except DiscordAPIError as e:
            log.warning("React failed: %s", e)
            return False

    async def close(self) -> None:
        if self._session and not self._session.closed and self._owns_session:
            await self._session.close()


class DiscordAPIError(Exception):
    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


class ZenLLM:
    """Client for the OpenCode Zen completion API (OpenAI-compatible)."""

    def __init__(
        self,
        base_url: str = "https://opencode.ai/zen/v1",
        api_key: str = "",
        model: str = "deepseek-v4-flash",
        temperature: float = 0.9,
        max_tokens: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def complete(
        self,
        messages: List[Dict[str, str]],
    ) -> Optional[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        url = f"{self.base_url}/chat/completions"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    log.warning("ZenLLM request %s -> %s: %s", resp.status, url, text[:200])
                    return None
                data = await resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError):
            log.warning("Unexpected ZenLLM response shape")
            return None
