"""Posting to a Discord webhook."""
import json
import time
import urllib.error
import urllib.request

from . import config

LIMIT = 1900  # Discord's hard limit is 2000; leave room.


def send(content, webhook=None):
    webhook = webhook or config.DISCORD_WEBHOOK_URL
    if len(content) > LIMIT:
        content = content[: LIMIT - 1] + "…"

    if config.DRY_RUN or not webhook:
        print("--- would send ---")
        print(content)
        return True

    body = json.dumps({"content": content, "allowed_mentions": {"parse": []}})
    req = urllib.request.Request(
        webhook,
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": config.USER_AGENT},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20):
                return True
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 5
                try:
                    wait = float(json.loads(e.read().decode()).get("retry_after", 5))
                except Exception:
                    pass
                time.sleep(min(wait, 30))
                continue
            print(f"Discord rejected the message ({e.code}): {e.reason}")
            return False
        except urllib.error.URLError as e:
            print(f"Could not reach Discord: {e}")
            time.sleep(3)
    return False


def send_all(contents):
    sent = 0
    for i, content in enumerate(contents):
        if send(content):
            sent += 1
        if i + 1 < len(contents):
            time.sleep(1)  # stay well under Discord's rate limit
    return sent
