import asyncio
import json
import logging
import random
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

log = logging.getLogger("discord_net.browser")

DISCORD_URL = "https://discord.com/channels/@me"


class SessionData:
    """Persistent session info for an account."""

    def __init__(self, profile_dir: str) -> None:
        self.path = Path(profile_dir) / "session.json"
        self.token: str = ""
        self.email: str = ""
        self.user_id: str = ""
        self.username: str = ""
        self.cookies: list = []
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.token = data.get("token", "")
                self.email = data.get("email", "")
                self.user_id = data.get("user_id", "")
                self.username = data.get("username", "")
                self.cookies = data.get("cookies", [])
            except Exception:
                pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "token": self.token,
            "email": self.email,
            "user_id": self.user_id,
            "username": self.username,
            "cookies": self.cookies,
        }
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class BrowserAccount:
    """Manages a single Discord account via Playwright with a persistent profile."""

    def __init__(
        self,
        name: str,
        token: str,
        profile_dir: str,
        headless: bool = False,
        email: str = "",
        password: str = "",
    ) -> None:
        self.name = name
        self.token = token
        self.profile_dir = profile_dir
        self.headless = headless
        self.email = email
        self.password = password
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._ready = False
        self.session = SessionData(profile_dir)
        if not self.token and self.session.token:
            self.token = self.session.token

    async def start(self) -> None:
        """Launch browser with persistent profile and load Discord."""
        self._playwright = await async_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ]

        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            headless=self.headless,
            args=launch_args,
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0.0.0 Safari/537.36"
            ),
            locale="en-GB",
            timezone_id="Asia/Karachi",
            ignore_https_errors=True,
        )

        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
        """)

        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()

        # Ensure we're on Discord
        if "discord.com" not in self._page.url:
            await self._page.goto("https://discord.com/app", wait_until="domcontentloaded")
            await asyncio.sleep(2)

        if self.token:
            await self._login_with_token()

        if not self._ready and self.email and self.password:
            await self._login_with_email()

        if self._ready:
            await self._save_session()

        if not self._ready:
            log.error("[%s] browser failed to login", self.name)

    async def _save_session(self) -> None:
        """Save session data (token, cookies, user info)."""
        try:
            token = await self._page.evaluate("""() => {
                try {
                    return localStorage.getItem('token');
                } catch(e) {
                    return null;
                }
            }""")
            if token:
                self.token = token.strip('"')
                self.session.token = self.token

            user_info = await self._page.evaluate("""() => {
                try {
                    const user = window.webpackChunkdiscord_app?.push?.[[0],{},req=>{
                        for(const m of Object.values(req.c)){
                            if(m?.exports?.default?.getCurrentUser){
                                return m.exports.default.getCurrentUser();
                            }
                        }
                    }];
                    return user ? { id: user.id, username: user.username } : null;
                } catch(e) {
                    return null;
                }
            }""")
            if user_info:
                self.session.user_id = user_info.get("id", "")
                self.session.username = user_info.get("username", "")

            cookies = await self._context.cookies()
            self.session.cookies = [
                {"name": c["name"], "value": c["value"], "domain": c["domain"]}
                for c in cookies
                if "discord.com" in c.get("domain", "")
            ]

            self.session.email = self.email
            self.session.save()
            log.info("[%s] session saved (user: %s)", self.name, self.session.username)
        except Exception as e:
            log.warning("[%s] failed to save session: %s", self.name, e)

    async def _login_with_token(self) -> None:
        """Login using auth token via localStorage."""
        try:
            await self._page.goto("https://discord.com/app", wait_until="domcontentloaded")
            await asyncio.sleep(3)

            await self._page.evaluate(f"""() => {{
                try {{
                    localStorage.setItem('token', '"{self.token}"');
                }} catch(e) {{}}
            }}""")
            await self._page.reload(wait_until="domcontentloaded")
            await asyncio.sleep(5)

            try:
                await self._page.wait_for_selector('[data-list-item-id="guildsnav"], [class*="guilds"]', timeout=15000)
                self._ready = True
                log.info("[%s] browser ready via token", self.name)
                await self._save_session()
            except Exception:
                log.debug("[%s] token login failed", self.name)
        except Exception as e:
            log.debug("[%s] token login error: %s", self.name, e)

    async def _login_with_email(self) -> None:
        """Login using email and password."""
        try:
            log.info("[%s] attempting email login...", self.name)
            await self._page.goto("https://discord.com/login", wait_until="domcontentloaded")
            await asyncio.sleep(3)

            email_input = await self._page.wait_for_selector('input[name="email"]', timeout=10000)
            if email_input:
                await email_input.click()
                await email_input.type(self.email, delay=random.randint(30, 80))
                await asyncio.sleep(0.5)

            password_input = await self._page.wait_for_selector('input[name="password"]', timeout=5000)
            if password_input:
                await password_input.click()
                await password_input.type(self.password, delay=random.randint(30, 80))
                await asyncio.sleep(0.5)

            login_button = await self._page.wait_for_selector('button[type="submit"]', timeout=5000)
            if login_button:
                await login_button.click()
                await asyncio.sleep(8)

            try:
                await self._page.wait_for_selector('[data-list-item-id="guildsnav"], [class*="guilds"]', timeout=20000)
                self._ready = True
                log.info("[%s] browser ready via email login", self.name)

                token = await self._page.evaluate("""() => {
                    try {
                        return localStorage.getItem('token');
                    } catch(e) {
                        return null;
                    }
                }""")
                if token:
                    self.token = token.strip('"')
                    log.info("[%s] extracted token from browser session", self.name)

                await self._save_session()
            except Exception:
                log.warning("[%s] email login may have failed", self.name)

        except Exception as e:
            log.warning("[%s] email login error: %s", self.name, e)

    async def login_outlook(self) -> bool:
        """Login to Outlook with email/password to establish session."""
        log.info("[%s] logging into Outlook for %s...", self.name, self.email)
        try:
            await self._page.goto("https://outlook.live.com/mail/0/", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            if "mail" in self._page.url and "login" not in self._page.url:
                log.info("[%s] already logged into Outlook", self.name)
                return True

            email_input = self._page.locator('input[name="loginfmt"]')
            if await email_input.count() > 0:
                await email_input.click()
                await asyncio.sleep(0.3)
                await email_input.type(self.email, delay=random.randint(30, 80))

            next_btn = self._page.locator('#idSIButton9')
            if await next_btn.count() > 0:
                await next_btn.click()
                await asyncio.sleep(2)

            pw_input = self._page.locator('input[name="passwd"]')
            if await pw_input.count() > 0:
                await pw_input.click()
                await asyncio.sleep(0.3)
                await pw_input.type(self.password, delay=random.randint(30, 80))

            sign_in_btn = self._page.locator('#idSIButton9')
            if await sign_in_btn.count() > 0:
                await sign_in_btn.click()
                await asyncio.sleep(3)

            stay_signed_btn = self._page.locator('#idSIButton9')
            if await stay_signed_btn.count() > 0:
                await stay_signed_btn.click()
                await asyncio.sleep(2)

            if "mail" in self._page.url:
                log.info("[%s] Outlook login successful!", self.name)
                return True
            else:
                log.warning("[%s] Outlook login may have failed, URL: %s", self.name, self._page.url)
                return False

        except Exception as e:
            log.error("[%s] Outlook login error: %s", self.name, e)
            return False

    async def send_message(self, channel_url: str, content: str) -> bool:
        """Send a message in a Discord channel via the browser."""
        if not self._ready or not self._page:
            return False

        try:
            current = self._page.url
            if channel_url not in current:
                await self._page.goto(channel_url, wait_until="networkidle")
                await asyncio.sleep(2)

            # Target the message input inside channelTextArea, not the search box
            selector = '[class*="channelTextArea"] [data-slate-editor="true"]'
            await self._page.wait_for_selector(selector, timeout=10000)
            editor = await self._page.query_selector(selector)
            if not editor:
                # Fallback: try the last slate editor on the page (message input is usually last)
                editors = await self._page.query_selector_all('[data-slate-editor="true"]')
                if editors:
                    editor = editors[-1]
                else:
                    log.warning("[%s] chat input not found", self.name)
                    return False

            await editor.click()
            await asyncio.sleep(0.3)

            for char in content:
                await self._page.keyboard.type(char, delay=random.randint(30, 80))
                if random.random() < 0.05:
                    await asyncio.sleep(random.uniform(0.2, 0.5))

            await asyncio.sleep(random.uniform(0.3, 0.8))
            await self._page.keyboard.press("Enter")
            await asyncio.sleep(1)

            log.info("[%s] sent message: %s", self.name, content[:60])
            return True

        except Exception as e:
            log.warning("[%s] send failed: %s", self.name, e)
            return False

    async def stop(self) -> None:
        """Close browser and save profile."""
        if self._context:
            await self._context.close()
        if self._playwright:
            await self._playwright.stop()
        self._ready = False


class BrowserEngine:
    """Manages multiple browser accounts for Discord."""

    def __init__(self, profile_base_dir: str = "browser_profiles") -> None:
        self.profile_base_dir = profile_base_dir
        self.accounts: dict[str, BrowserAccount] = {}

    def _profile_dir(self, name: str) -> str:
        return str(Path(self.profile_base_dir) / name)

    async def add_account(
        self,
        name: str,
        token: str,
        headless: bool = False,
        email: str = "",
        password: str = "",
    ) -> BrowserAccount:
        account = BrowserAccount(
            name=name,
            token=token,
            profile_dir=self._profile_dir(name),
            headless=headless,
            email=email,
            password=password,
        )
        self.accounts[name] = account
        return account

    async def start_all(self) -> None:
        for name, account in self.accounts.items():
            try:
                await account.start()
            except Exception as e:
                log.error("[%s] failed to start browser: %s", name, e)
            if name != list(self.accounts.keys())[-1]:
                await asyncio.sleep(random.uniform(10, 25))

    async def stop_all(self) -> None:
        for account in self.accounts.values():
            await account.stop()
