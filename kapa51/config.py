"""Configuration, all overridable via environment variables."""
import os

SEASON = int(os.environ.get("SEASON", "2027"))
SUBSERIE_ID = int(os.environ.get("SUBSERIE_ID", "3505"))
LEVEL_ID = int(os.environ.get("LEVEL_ID", "94"))
TEAM_ID = int(os.environ.get("TEAM_ID", "1368625759"))  # KaPa-51, U15 Valkoinen
TEAM_NAME = os.environ.get("TEAM_NAME", "KaPa-51")

TIMEZONE = os.environ.get("TIMEZONE", "Europe/Helsinki")

# How many days ahead the daily schedule scan looks.
SCHEDULE_DAYS = int(os.environ.get("SCHEDULE_DAYS", "30"))
# How long before puck drop the "starting soon" message is sent.
STARTING_SOON_MINUTES = int(os.environ.get("STARTING_SOON_MINUTES", "60"))
# Seconds between requests when scanning many dates.
SCAN_DELAY_SECONDS = float(os.environ.get("SCAN_DELAY_SECONDS", "2"))

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

STATE_PATH = os.environ.get("STATE_PATH", "state.json")
ARCHIVE_DIR = os.environ.get("ARCHIVE_DIR", "archive")
ARCHIVE_RAW = os.environ.get("ARCHIVE_RAW", "1").lower() in ("1", "true", "yes")

# Sent with every request so the site's operators can see who we are.
CONTACT = os.environ.get("CONTACT", "")
USER_AGENT = os.environ.get(
    "USER_AGENT",
    "KaPa-51-game-notifier/1.0 (team Discord notifications; low rate)"
    + (f" contact: {CONTACT}" if CONTACT else ""),
)
