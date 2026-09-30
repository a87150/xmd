#!/usr/bin/env python3
"""Self-check for xmd.cookies.ensure_netscape_cookies. Run: python -m xmd.selftest"""
import json
import shutil
from pathlib import Path

from .cookies import ensure_netscape_cookies, validate_cookies
from .gallery import parse_gallery_messages

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
        "cookies.txt",
        "# Netscape HTTP Cookie File\n"
        ".x.com\tTRUE\t/\tTRUE\t0\tauth_token\tsecret\n"
        ".x.com\tTRUE\t/\tTRUE\t0\tct0\tcsrf\n",
    )
    assert ensure_netscape_cookies(src) == src, "existing netscape file must pass through"


def test_rejects_netscape_file_with_expired_auth_token():
    src = _write(
        "expired.txt",
        "# Netscape HTTP Cookie File\n"
        ".x.com\tTRUE\t/\tTRUE\t1000000000\tauth_token\told\n",
    )
    try:
        ensure_netscape_cookies(src)
    except RuntimeError as exc:
        assert "expired" in str(exc), str(exc)
    else:
        raise AssertionError("an expired auth_token in a netscape file must be rejected")


def test_surfaces_embedded_gallery_errors():
    # gallery-dl exits 0 and hides failures as [-1, {...}] in its JSON stream.
    payload = json.dumps([[-1, {"error": "OperationalError", "message": "readonly database"}]])
    try:
        parse_gallery_messages(payload)
    except RuntimeError as exc:
        assert "OperationalError" in str(exc), f"error name lost: {exc}"
        assert "readonly database" in str(exc), f"error detail lost: {exc}"
    else:
        raise AssertionError("error-only stream must raise, not return 0 items")


def test_keeps_items_when_some_fail():
    payload = json.dumps(
        [
            [3, "https://pbs.twimg.com/media/a.jpg", {"num": 1}],
            [-1, {"error": "HttpError", "message": "404"}],
        ]
    )
    items = parse_gallery_messages(payload)
    assert len(items) == 1, f"a per-item error must not discard good items: {items}"
    assert items[0]["url"].endswith("a.jpg")


def test_rejects_missing_auth_token():
    try:
        validate_cookies({"guest_id": None})
    except RuntimeError as exc:
        assert "auth_token" in str(exc), str(exc)
    else:
        raise AssertionError("a cookie set without auth_token cannot authenticate")


def test_rejects_expired_auth_token():
    try:
        validate_cookies({"auth_token": 1_000_000.0, "ct0": None})
    except RuntimeError as exc:
        assert "expired" in str(exc), str(exc)
    else:
        raise AssertionError("an expired auth_token must be rejected")


def test_accepts_valid_cookies_and_tolerates_missing_ct0():
    future = 4_000_000_000.0
    # A missing ct0 is not fatal: gallery-dl generates one.
    validate_cookies({"auth_token": future})
    validate_cookies({"auth_token": future, "ct0": future})
    # A session cookie declares no expiry and must not be treated as expired.
    validate_cookies({"auth_token": None})


def test_json_export_without_auth_token_is_rejected_before_conversion():
    src = _write("bad.json", json.dumps([{"name": "guest_id", "value": "1"}]))
    try:
        ensure_netscape_cookies(src)
    except RuntimeError:
        pass
    else:
        raise AssertionError("conversion must not silently accept unusable cookies")
    converted = src.with_name(src.stem + ".netscape" + src.suffix)
    assert not converted.exists(), "no converted file should be written when validation fails"


def main():
    try:
        test_converts_json_export()
        test_passes_through_netscape_file()
        test_surfaces_embedded_gallery_errors()
        test_keeps_items_when_some_fail()
        test_rejects_missing_auth_token()
        test_rejects_expired_auth_token()
        test_accepts_valid_cookies_and_tolerates_missing_ct0()
        test_json_export_without_auth_token_is_rejected_before_conversion()
        test_rejects_netscape_file_with_expired_auth_token()
        print("ok - 9 checks passed")
        return 0
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
