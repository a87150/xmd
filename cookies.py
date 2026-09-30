"""Cookie file handling, including JSON-to-Netscape conversion."""



from __future__ import annotations

import json
from pathlib import Path





def ensure_netscape_cookies(path: Path) -> Path:
    """Convert a JSON cookie export into Netscape cookies.txt for gallery-dl -C."""
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return path

    if not isinstance(entries, list):
        return path

    lines = [
        "# Netscape HTTP Cookie File",
        "# Converted from JSON export by download_x_media.py",
        "",
    ]
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
        expires_text = str(int(expires)) if isinstance(expires, (int, float)) else "0"
        lines.append(
            "\t".join(
                [
                    domain,
                    "TRUE" if include_subdomains else "FALSE",
                    str(entry.get("path") or "/"),
                    "TRUE" if entry.get("secure") else "FALSE",
                    expires_text,
                    str(name),
                    str(value),
                ]
            )
        )

    converted = path.with_name(path.stem + ".netscape" + path.suffix)
    converted.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return converted
