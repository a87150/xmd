"""Shared constants and extension sets."""



from __future__ import annotations

import re
from pathlib import Path





HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")

DEFAULT_OUTPUT_ROOT = Path("downloads")

DEFAULT_VENV_DIR = Path(".venv")

DEFAULT_COOKIES_FILE = Path("cookies.json")

# gallery-dl's own default lives under %APPDATA%, which can be read-only (Defender
# Controlled Folder Access, locked DB, roaming profile). The tool already requires
# the working directory to be writable because it creates downloads/ there, so the
# cache goes next to it instead of adding a second, fragile location.
DEFAULT_CACHE_FILE = Path(".gallery-dl-cache.sqlite3")

RESERVED_PATHS = {
    "account",
    "compose",
    "download",
    "explore",
    "hashtag",
    "home",
    "i",
    "intent",
    "jobs",
    "login",
    "messages",
    "notifications",
    "privacy",
    "search",
    "settings",
    "share",
    "signup",
    "tos",
}

SUPPORTED_HOSTS = {
    "mobile.twitter.com",
    "mobile.x.com",
    "twitter.com",
    "www.twitter.com",
    "www.x.com",
    "x.com",
}

AUTO_COOKIE_BROWSERS = (
    "firefox",
    "chrome",
    "brave",
    "edge",
    "chromium",
    "safari",
    "vivaldi",
    "opera",
)

# Browsers that encrypt cookies with Chromium app-bound encryption (v127+),
# which gallery-dl cannot decrypt.
CHROMIUM_BROWSERS = frozenset(
    {"chrome", "chromium", "edge", "brave", "vivaldi", "opera", "thorium"}
)

AUTH_REQUIRED_MARKERS = (
    "AuthRequired",
    "authenticated cookies needed to access this timeline",
)

COOKIE_DB_MISSING_MARKERS = (
    "unable to find",
    "cookies database",
)

SUMMARY_FILENAME = "download-summary.json"

IMAGES_SUBDIR = "images"

VIDEOS_SUBDIR = "videos"

DOWNLOAD_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}

VIDEO_EXTENSIONS = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ts",
    ".webm",
}

MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
