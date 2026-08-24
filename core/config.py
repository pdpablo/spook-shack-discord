import os
from dotenv import load_dotenv

# =====================================================
# LOAD ENV
# =====================================================
load_dotenv()

# =====================================================
# DISCORD CORE
# =====================================================
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# =====================================================
# PUBLIC CHANNELS
# =====================================================
SIGNAL_ENTRY_CHANNEL_ID = int(os.getenv("SIGNAL_ENTRY_CHANNEL_ID", "0"))
PARANORMAL_DISCUSSION_CHANNEL_ID = int(os.getenv("PARANORMAL_DISCUSSION_CHANNEL_ID", "0"))
SHACK_LOUNGE_CHANNEL_ID = int(os.getenv("SHACK_LOUNGE_CHANNEL_ID", "0"))
PASTEBIN_CHANNEL_ID = int(os.getenv("PASTEBIN_CHANNEL_ID", "0"))

# =====================================================
# INNER SHACK
# =====================================================
PH_CHANNEL_ID = int(os.getenv("PH_CHANNEL_ID", "0"))
GLOBAL_CHANNEL_ID = int(os.getenv("GLOBAL_CHANNEL_ID", "0"))
DISCORD_FORUM_CHANNEL_ID = int(os.getenv("DISCORD_FORUM_CHANNEL_ID", "0"))
NVD_CVE_CHANNEL_ID = int(os.getenv("NVD_CVE_CHANNEL_ID", "0"))
CHANNEL_BREACH = int(os.getenv("CHANNEL_BREACH", "0"))

# =====================================================
# THREAT CLUSTER
# =====================================================
CHANNEL_RANSOMWARE = int(os.getenv("CHANNEL_RANSOMWARE", "0"))
CHANNEL_VULNERABILITY = int(os.getenv("CHANNEL_VULNERABILITY", "0"))
CHANNEL_APT = int(os.getenv("CHANNEL_APT", "0"))
CHANNEL_GENERAL = int(os.getenv("CHANNEL_GENERAL", "0"))

# =====================================================
# RESTRICTED / COMMAND CHANNELS
# =====================================================
THREAT_ACTOR_FORUM_ID = int(os.getenv("THREAT_ACTOR_FORUM_ID", "0"))
CHANNEL_ONION = int(os.getenv("CHANNEL_ONION", "0"))
SEARCH_CHANNEL_ID = int(os.getenv("SEARCH_CHANNEL_ID", "0"))
CREEPY_CRAWLIES_FORUM_ID = int(os.getenv("CREEPY_CRAWLIES_FORUM_ID", "0"))

TAKEDOWN_COMMAND_CHANNEL_ID = int(os.getenv("TAKEDOWN_COMMAND_CHANNEL_ID", "0"))
TAKEDOWN_FORUM_CHANNEL_ID = int(os.getenv("TAKEDOWN_FORUM_CHANNEL_ID", "0"))

REPORT_COMMAND_CHANNEL_ID = int(os.getenv("REPORT_COMMAND_CHANNEL_ID", "0"))
REPORT_FORUM_CHANNEL_ID = int(os.getenv("REPORT_FORUM_CHANNEL_ID", "0"))
SHODAN_SEARCH_CHANNEL_ID = int(os.getenv("SHODAN_SEARCH_CHANNEL_ID", "0"))

SPOOK_CHANNEL_ID = int(os.getenv("SPOOK_CHANNEL_ID", "0"))
CHANNEL_BREACH = int(os.getenv("CHANNEL_BREACH", "0"))
ACTOR_DOSSIER_CHANNEL_ID = int(os.getenv("ACTOR_DOSSIER_CHANNEL_ID", "0"))
ACTOR_DOSSIER_FORUM_ID = int(os.getenv("ACTOR_DOSSIER_FORUM_ID", "0"))
# =====================================================
# TELEGRAM
# =====================================================
TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH")
TG_CHANNEL = os.getenv("TG_CHANNEL")

# =====================================================
# EXTERNAL APIs
# =====================================================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
HIBP_API_KEY = os.getenv("HIBP_API_KEY")
OTX_API_KEY = os.getenv("OTX_API_KEY")
NVD_API_KEY = os.getenv("NVD_API_KEY")
RANSOMWARELIVE_API_TOKEN = os.getenv("RANSOMWARELIVE_API_TOKEN")
SHODAN_API_KEY = os.getenv("SHODAN_API_KEY")

# =====================================================
# MISP
# =====================================================
MISP_FEED_URL = os.getenv("MISP_FEED_URL")

# =====================================================
# NGINX / CREEPY CRAWLIES
# =====================================================
NGINX_ACCESS_LOG = os.getenv(
    "NGINX_ACCESS_LOG",
    "/var/log/nginx/access.log"
)

SPOOK_SHACK_HOST = os.getenv(
    "SPOOK_SHACK_HOST",
    "spook-shack.com"
).lower()

# =====================================================
# ORG / TEMPLATES
# =====================================================
ORG_NAME = os.getenv("ORG_NAME", "Spook Shack")
ORG_CONTACT_EMAIL = os.getenv("ORG_CONTACT_EMAIL", "security@spook-shack.com")

# =====================================================
# RUNTIME
# =====================================================
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "3600"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# =====================================================
# SANITY CHECKS (FAIL FAST, CLEAR ERRORS)
# =====================================================
if not DISCORD_BOT_TOKEN:
    raise RuntimeError("DISCORD_BOT_TOKEN is not set")


