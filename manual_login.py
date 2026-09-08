"""
Manual Discord login helper.
Opens browser, fills credentials, waits for you to complete CAPTCHA.
Saves session so future runs skip login.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from playwright.async_api import async_playwright


async def manual_login(email: str, password: str, profile_dir: str):
    print(f"Opening browser for {email}...")
    print("Complete any CAPTCHA or verification manually.")
    print("Once you see Discord's main page, press Enter in this terminal.\n")

    pw = await async_playwright().start()

    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
    ]

    context = await pw.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=False,
        args=launch_args,
        viewport={"width": 1400, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/152.0.0.0 Safari/537.36"
        ),
        locale="en-GB",
        timezone_id="Asia/Karachi",
        ignore_https_errors=True,
    )

    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        window.chrome = { runtime: {} };
    """)

    page = context.pages[0] if context.pages else await context.new_page()

    # Navigate to Discord login
    await page.goto("https://discord.com/login", wait_until="networkidle", timeout=30000)
    await asyncio.sleep(2)

    # Check if already logged in - if so, go to logout first
    if "channels" in page.url:
        print("Already logged in. Logging out first...")
        # Go to settings and logout
        await page.goto("https://discord.com/channels/@me", wait_until="networkidle")
        await asyncio.sleep(2)
        # Try to find and click logout
        try:
            logout_btn = page.locator('text=Log Out')
            if await logout_btn.count() > 0:
                await logout_btn.click()
                await asyncio.sleep(2)
        except:
            pass
        # Navigate back to login
        await page.goto("https://discord.com/login", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

    # Fill email
    email_input = page.locator('input[name="email"]')
    if await email_input.count() > 0:
        await email_input.click()
        await asyncio.sleep(0.3)
        await email_input.type(email, delay=50)
        print(f"Filled email: {email}")

    # Fill password
    pw_input = page.locator('input[name="password"]')
    if await pw_input.count() > 0:
        await pw_input.click()
        await asyncio.sleep(0.3)
        await pw_input.type(password, delay=50)
        print("Filled password")

    await asyncio.sleep(0.5)

    # Click login button
    login_btn = page.locator('button[type="submit"]')
    if await login_btn.count() > 0:
        await login_btn.click()
        print("Clicked login button")

    print("\n=== Complete any CAPTCHA/verification in the browser ===")
    input("Press Enter here AFTER you see Discord's main page...\n")

    # Navigate to Discord app to ensure we're on the right page
    await page.goto("https://discord.com/channels/@me", wait_until="networkidle", timeout=30000)
    await asyncio.sleep(5)

    # Get storage state which includes localStorage
    token = None
    try:
        storage = await context.storage_state()
        # Check origins for token
        for origin in storage.get("origins", []):
            if "discord.com" in origin.get("origin", ""):
                for item in origin.get("localStorage", []):
                    if item.get("name") == "token":
                        token = item.get("value", "")
                        break
    except Exception as e:
        print(f"Storage state method failed: {e}")

    if token:
        token = token.strip('"')
        print(f"\nToken obtained: {token[:30]}...")
    else:
        print("\nCould not extract token automatically.")
        print("The cookies are saved and the bot may still work.")

    # Get user info from the page
    user_info = None
    try:
        user_info = await page.evaluate("""() => {
            try {
                // Try to get username from the page
                const usernameEl = document.querySelector('[data-testid="user-tagline-username"]');
                if (usernameEl) return { username: usernameEl.textContent };
                
                // Try to get from the DOM
                const nameEl = document.querySelector('.nameTag-2_SxGQ');
                if (nameEl) return { username: nameEl.textContent };
                
                // Try to get from webpack
                let user = null;
                if (window.webpackChunkdiscord_app) {
                    window.webpackChunkdiscord_app.push([[Math.random()], {}, req => {
                        for (const m of Object.values(req.c)) {
                            try {
                                if (m?.exports?.default?.getCurrentUser) {
                                    user = m.exports.default.getCurrentUser();
                                    break;
                                }
                            } catch(e) {}
                        }
                    }]);
                }
                return user ? { id: user.id, username: user.username } : null;
            } catch(e) {
                return null;
            }
        }""")
    except:
        pass

    # Get cookies
    cookies = await context.cookies()
    discord_cookies = [
        {"name": c["name"], "value": c["value"], "domain": c["domain"]}
        for c in cookies
        if "discord.com" in c.get("domain", "")
    ]

    # Save session
    session_path = Path(profile_dir) / "session.json"
    session_data = {
        "token": token or "",
        "email": email,
        "user_id": user_info.get("id", "") if user_info else "",
        "username": user_info.get("username", "") if user_info else "",
        "cookies": discord_cookies,
    }
    session_path.write_text(json.dumps(session_data, indent=2), encoding="utf-8")
    print(f"Session saved to {session_path}")

    if user_info:
        print(f"Logged in as: {user_info.get('username', 'unknown')} (ID: {user_info.get('id', 'unknown')})")
    
    if token:
        print(f"\nYou can now use this token in config.json or the bot will use the saved session.")
    else:
        print("\nToken extraction failed, but cookies are saved.")
        print("The bot may still work with the saved cookies.")

    await context.close()
    await pw.stop()
    return token


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manual Discord login helper")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--profile", default="browser_profiles/account1")
    args = parser.parse_args()

    asyncio.run(manual_login(args.email, args.password, args.profile))
