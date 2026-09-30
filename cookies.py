"""Cookie file handling, including JSON-to-Netscape conversion and validation."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# gallery-dl declares only auth_token as a required cookie
# (gallery_dl/extractor/twitter.py: cookies_names = ("auth_token",)) and it
# generates a ct0 itself when one is missing, so a missing ct0 is only a warning.
REQUIRED_COOKIE = "auth_token"
RECOMMENDED_COOKIE = "ct0"


def _read_netscape_cookies(text: str) -> dict[str, float | None]:
    """Parse name -> expiry (epoch seconds, None for a session cookie)."""
    cookies: dict[str, float | None] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 7:
            continue
        name, expires = fields[5], fields[4]
        try:
            stamp: float | None = float(expires)
        except ValueError:
            stamp = None
        if stamp == 0:
            stamp = None
        cookies[name] = stamp
    return cookies


def validate_cookies(cookies: dict[str, float | None]) -> None:
    """Raise when the cookie set cannot authenticate; warn about ct0.

    Expiry is only checked when the export states one explicitly, so session
    cookies are never reported as expired.
    """
    now = time.time()
    fatal: list[str] = []

    if REQUIRED_COOKIE not in cookies:
        fatal.append(f"missing {REQUIRED_COOKIE}")
    else:
        expires = cookies[REQUIRED_COOKIE]
        if expires is not None and expires <= now:
            days = int((now - expires) / 86400)
            fatal.append(f"{REQUIRED_COOKIE} expired {days} day(s) ago")

    if fatal:
        raise RuntimeError(
            "; ".join(fatal)
            + ". X cannot be read without it. Re-export fresh cookies from a "
            "logged-in x.com session (see README)."
        )

    if RECOMMENDED_COOKIE not in cookies:
        print(
            f"[cookies] warning: {RECOMMENDED_COOKIE} is absent; gallery-dl will "
            "generate one, which X may reject. Prefer a full x.com export.",
            file=sys.stderr,
        )
    else:
        expires = cookies[RECOMMENDED_COOKIE]
        if expires is not None and expires <= now:
            print(
                f"[cookies] warning: {RECOMMENDED_COOKIE} has expired; gallery-dl "
                "will generate a replacement.",
                file=sys.stderr,
            )


def ensure_netscape_cookies(path: Path) -> Path:
    """Validate a cookie file, converting a JSON export into Netscape format."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return path

    try:
        entries = json.loads(text)
    except json.JSONDecodeError:
        entries = None

    if not isinstance(entries, list):
        # Already Netscape (or an unreadable format); judge it on its own contents
        # and let gallery-dl report anything we cannot parse.
        validate_cookies(_read_netscape_cookies(text))
        return path

    cookies: dict[str, float | None] = {}
    body: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        value = entry.get("value")
        if not name or value is None:
            continue
        domain = str(entry.get("domain") or "")
        host_only = entry.get("hostOnly")
        include_subdomains = (not host_only) if host_only is not None else domain.startswith(".")
        expires = entry.get("expirationDate")
        known = isinstance(expires, (int, float)) and not entry.get("session")
        cookies[str(name)] = float(expires) if known else None
        body.append(
            "\t".join(
                [
                    domain,
                    "TRUE" if include_subdomains else "FALSE",
                    str(entry.get("path") or "/"),
                    "TRUE" if entry.get("secure") else "FALSE",
                    str(int(expires)) if isinstance(expires, (int, float)) else "0",
                    str(name),
                    str(value),
                ]
            )
        )

    validate_cookies(cookies)

    converted = path.with_name(path.stem + ".netscape" + path.suffix)
    converted.write_text(
        "\n".join(
            [
                "# Netscape HTTP Cookie File",
                "# Converted from JSON export by xmd",
                "",
                *body,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return converted
