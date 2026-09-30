"""Turn user input (handle, @handle, URL) into a canonical handle and media URL."""



from __future__ import annotations

from urllib.parse import urlparse

from .constants import HANDLE_RE, RESERVED_PATHS, SUPPORTED_HOSTS





def normalize_profile(value: str) -> tuple[str, str]:
    candidate = value.strip()
    if not candidate:
        raise ValueError("Profile URL or handle cannot be empty.")

    if candidate.startswith("@"):
        handle = candidate[1:]
    elif HANDLE_RE.fullmatch(candidate):
        handle = candidate
    else:
        if "://" not in candidate:
            candidate = f"https://{candidate}"
        parsed = urlparse(candidate)
        host = parsed.netloc.lower()
        if host not in SUPPORTED_HOSTS:
            raise ValueError(
                f"Unsupported host '{parsed.netloc}'. Use a twitter.com or x.com profile URL."
            )
        segments = [segment for segment in parsed.path.split("/") if segment]
        if not segments:
            raise ValueError("The supplied URL does not look like a profile URL.")
        handle = segments[0].lstrip("@")

    if handle.lower() in RESERVED_PATHS or not HANDLE_RE.fullmatch(handle):
        raise ValueError(
            "Could not extract a valid Twitter/X handle. "
            "Expected a profile URL or handle like @example_user."
        )

    return handle, f"https://x.com/{handle}/media"
