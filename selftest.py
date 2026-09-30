#!/usr/bin/env python3
"""Self-check for xmd.cookies.ensure_netscape_cookies. Run: python -m xmd.selftest"""
import json
import shutil
from pathlib import Path

from .cookies import ensure_netscape_cookies

SCRATCH = Path(__file__).resolve().parent.parent / "_scratch_cookies"


def _write(name, text):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = SCRATCH / name
    path.write_text(text, encoding="utf-8")
    return path


def test_converts_json_export():
    payload = [
        {
            "domain": ".x.com",
            "expirationDate": 1822327700.76,
            "hostOnly": False,
            "httpOnly": True,
            "name": "auth_token",
            "path": "/",
            "secure": True,
            "session": False,
            "value": "abc123",
        },
        {
            "domain": "x.com",
            "hostOnly": True,
            "name": "csrf",
            "path": "/",
            "secure": True,
            "value": "tok",
        },
        {"name": "no_value_cookie", "domain": ".x.com"},
    ]
    src = _write("cookies.json", json.dumps(payload))

    out = ensure_netscape_cookies(src)
    assert out != src, "conversion should produce a new file"

    rows = [
        line
        for line in out.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    assert len(rows) == 2, f"entries missing name/value must be dropped, got {len(rows)}"

    auth = rows[0].split("\t")
    assert len(auth) == 7, f"netscape rows need 7 tab-separated fields, got {len(auth)}"
    assert auth[0] == ".x.com"
    assert auth[1] == "TRUE", "domain cookie (.x.com) must include subdomains"
    assert auth[2] == "/"
    assert auth[3] == "TRUE", "secure flag"
    assert auth[4] == "1822327700", "expiration truncated to int seconds"
    assert auth[5] == "auth_token"
    assert auth[6] == "abc123"

    csrf = rows[1].split("\t")
    assert csrf[1] == "FALSE", "hostOnly cookie must not include subdomains"
    assert csrf[4] == "0", "missing expiration must be 0 (session cookie)"


def test_passes_through_netscape_file():
    src = _write(
        "cookies.txt", "# Netscape HTTP Cookie File\n.x.com\tTRUE\t/\tTRUE\t0\ta\tb\n"
    )
    assert ensure_netscape_cookies(src) == src, "existing netscape file must pass through"


def main():
    try:
        test_converts_json_export()
        test_passes_through_netscape_file()
        print("ok - 2 checks passed")
        return 0
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
