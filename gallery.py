"""Build and run gallery-dl / yt-dlp commands, including auth preflight."""



from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Iterable
from urllib.request import Request, urlopen

from .constants import (
    AUTO_COOKIE_BROWSERS,
    AUTH_REQUIRED_MARKERS,
    CHROMIUM_BROWSERS,
    COOKIE_DB_MISSING_MARKERS,
    DOWNLOAD_USER_AGENT,
)

from .media import archive_key_from_metadata, insert_archive_entry, load_archive_keys, target_path_for_media





def build_gallery_dl_command(
    gallery_bin: Path,
    target_url: str,
    target_dir: Path,
    archive_file: Path,
    args: argparse.Namespace,
    browser_override: str | None = None,
) -> list[str]:
    command = [
        str(gallery_bin),
        "-D",
        str(target_dir),
        "--download-archive",
        str(archive_file),
        "-o",
        "extractor.twitter.timeline.strategy=media",
        "-o",
        f"extractor.twitter.pinned={str(not args.exclude_pinned).lower()}",
        "-o",
        f"extractor.twitter.quoted={str(args.include_quoted).lower()}",
        "-o",
        f"extractor.twitter.retweets={'original' if args.include_retweets else 'false'}",
        "-o",
        "extractor.twitter.videos=ytdl",
        "-o",
        "extractor.twitter.text-tweets=false",
        "-o",
        "extractor.twitter.ratelimit=wait",
    ]

    if args.cookies_file:
        command.extend(["-C", str(args.cookies_file.expanduser().resolve())])
    elif browser_override or args.cookies_browser:
        command.extend(["--cookies-from-browser", browser_override or args.cookies_browser])

    if args.cache_file:
        command.extend(["--cache-file", str(args.cache_file.expanduser().resolve())])

    if args.write_info_json:
        command.append("--write-info-json")

    command.append(target_url)
    return command

def quoted_command(parts: Iterable[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)

def extract_media_items(command: list[str], env: dict[str, str]) -> list[dict[str, object]]:
    discovery_command = [command[0], "-q", "-s", "-j", *command[1:]]
    result = subprocess.run(
        discovery_command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(stderr or f"gallery-dl exited with status {result.returncode}")

    payload = result.stdout.strip()
    if not payload:
        return []
    return parse_gallery_messages(payload)


def parse_gallery_messages(payload: str) -> list[dict[str, object]]:
    """Turn gallery-dl's -j JSON stream into media items, surfacing embedded errors."""
    try:
        messages = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"failed to parse gallery-dl JSON output: {exc}") from exc

    items: list[dict[str, object]] = []
    errors: list[str] = []
    for entry in messages:
        # gallery-dl exits 0 and reports failures as [-1, {"error": ...}] inside the
        # JSON stream. Those were silently dropped, turning every failure into
        # "found 0 media". Collect them and surface them instead.
        if isinstance(entry, list) and len(entry) >= 2 and isinstance(entry[1], dict):
            if "error" in entry[1]:
                label = entry[1].get("error")
                detail = entry[1].get("message") or entry[1].get("exception") or ""
                errors.append(f"{label}: {detail}".rstrip(": "))
                continue
        if (
            isinstance(entry, list)
            and len(entry) >= 3
            and entry[0] == 3
            and isinstance(entry[1], str)
            and isinstance(entry[2], dict)
        ):
            items.append({"url": entry[1], "metadata": entry[2]})

    if errors and not items:
        raise RuntimeError("gallery-dl: " + "; ".join(dict.fromkeys(errors)))
    if errors:
        print(
            f"[warn] gallery-dl reported {len(errors)} error(s); continuing with "
            f"{len(items)} extracted item(s): {' | '.join(dict.fromkeys(errors))}",
            file=sys.stderr,
        )
    return items

def write_media_info_file(path: Path, source_url: str, metadata: dict[str, object]) -> None:
    info_path = path.with_suffix(path.suffix + ".info.json")
    info = dict(metadata)
    info["download_url"] = source_url
    with info_path.open("w", encoding="utf-8") as handle:
        json.dump(info, handle, indent=2)
        handle.write("\n")

def cleanup_partial_downloads(destination: Path) -> None:
    for candidate in (
        destination,
        destination.with_name(destination.name + ".part"),
        destination.with_name(destination.name + ".ytdl"),
    ):
        candidate.unlink(missing_ok=True)

def download_direct_file(url: str, destination: Path, timeout: int) -> None:
    temp_path = destination.with_name(destination.name + ".part")
    request = Request(url, headers={"User-Agent": DOWNLOAD_USER_AGENT})

    try:
        with urlopen(request, timeout=timeout) as response, temp_path.open("wb") as handle:
            shutil.copyfileobj(response, handle, length=1024 * 1024)
        temp_path.replace(destination)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

def build_ytdlp_command(
    ytdlp_bin: Path,
    source_url: str,
    destination: Path,
    args: argparse.Namespace,
    browser_override: str | None,
) -> list[str]:
    command = [
        str(ytdlp_bin),
        "--quiet",
        "--no-warnings",
        "--no-progress",
        "--socket-timeout",
        str(args.timeout),
        "--retries",
        str(args.retries),
        "--fragment-retries",
        str(args.retries),
        "--file-access-retries",
        str(args.retries),
        "-o",
        str(destination),
    ]

    if args.cookies_file:
        command.extend(["--cookies", str(args.cookies_file.expanduser().resolve())])
    elif browser_override or args.cookies_browser:
        command.extend(["--cookies-from-browser", browser_override or args.cookies_browser])

    command.append(source_url)
    return command

def download_media_item(
    item: dict[str, object],
    target_dir: Path,
    ytdlp_bin: Path,
    args: argparse.Namespace,
    browser_override: str | None,
    archive_file: Path,
    archive_lock: Lock,
) -> str:
    metadata = item["metadata"]
    url = str(item["url"])
    destination = target_path_for_media(target_dir, metadata, args.organize_media)
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None

    for attempt in range(1, args.retries + 1):
        try:
            cleanup_partial_downloads(destination)
            if url.startswith("ytdl:"):
                command = build_ytdlp_command(
                    ytdlp_bin,
                    url[5:],
                    destination,
                    args,
                    browser_override,
                )
                result = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if result.returncode != 0:
                    message = result.stderr.strip() or result.stdout.strip() or "yt-dlp failed"
                    raise RuntimeError(message)
            else:
                download_direct_file(url, destination, args.timeout)
            break
        except Exception as exc:
            last_error = exc
            cleanup_partial_downloads(destination)
            if attempt < args.retries:
                print(
                    f"[retry] {destination.name} attempt {attempt + 1}/{args.retries}",
                    file=sys.stderr,
                )
                time.sleep(min(2 ** (attempt - 1), 5))
            else:
                raise RuntimeError(str(last_error)) from last_error

    if args.write_info_json:
        write_media_info_file(destination, url, metadata)

    archive_key = archive_key_from_metadata(metadata)
    with archive_lock:
        insert_archive_entry(archive_file, archive_key)

    return str(destination.relative_to(target_dir))

def download_media_items(
    items: list[dict[str, object]],
    target_dir: Path,
    archive_file: Path,
    ytdlp_bin: Path,
    args: argparse.Namespace,
    browser_override: str | None,
) -> dict[str, object]:
    archive_keys = load_archive_keys(archive_file)
    pending: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    skipped = 0

    for item in items:
        metadata = item["metadata"]
        archive_key = archive_key_from_metadata(metadata)
        if archive_key in seen_keys:
            continue
        seen_keys.add(archive_key)

        destination = target_path_for_media(target_dir, metadata, args.organize_media)
        if archive_key in archive_keys or destination.exists():
            skipped += 1
            continue
        pending.append(item)

    total = len(pending)
    print(
        f"[queue] discovered={len(items)} pending={total} skipped={skipped} concurrency={args.concurrency}",
        file=sys.stderr,
    )
    if not pending:
        return {
            "exit_code": 0,
            "discovered": len(items),
            "pending": total,
            "skipped": skipped,
            "failures": [],
        }

    archive_lock = Lock()
    progress_lock = Lock()
    completed = 0
    failures: list[dict[str, str]] = []

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {
            executor.submit(
                download_media_item,
                item,
                target_dir,
                ytdlp_bin,
                args,
                browser_override,
                archive_file,
                archive_lock,
            ): item
            for item in pending
        }

        for future in as_completed(futures):
            item = futures[future]
            metadata = item["metadata"]
            relative_path = str(
                target_path_for_media(target_dir, metadata, args.organize_media).relative_to(target_dir)
            )
            with progress_lock:
                completed += 1
                progress = f"{completed}/{total}"

            try:
                saved_path = future.result()
            except Exception as exc:
                failures.append({"path": relative_path, "error": str(exc)})
                print(f"[failed] {progress} {relative_path}: {exc}", file=sys.stderr)
            else:
                print(f"[saved] {progress} {saved_path}", file=sys.stderr)

    if failures:
        print(f"[summary] {len(failures)} file(s) failed to download.", file=sys.stderr)
        for failure in failures[:10]:
            print(f"[failure] {failure['path']}: {failure['error']}", file=sys.stderr)

    return {
        "exit_code": 1 if failures else 0,
        "discovered": len(items),
        "pending": total,
        "skipped": skipped,
        "failures": failures,
    }

def run_preflight(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    preview_command = [command[0], "-s", "--post-range", "1", *command[1:]]
    return subprocess.run(
        preview_command,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

def is_auth_required(output: str, returncode: int) -> bool:
    lowered = output.lower()
    return returncode == 16 or any(marker.lower() in lowered for marker in AUTH_REQUIRED_MARKERS)

def is_cookie_db_missing(output: str) -> bool:
    lowered = output.lower()
    return all(marker in lowered for marker in COOKIE_DB_MISSING_MARKERS)

def browser_cookie_hint(tried: Iterable[str]) -> None:
    """Explain why reading cookies straight from a browser usually fails.

    gallery-dl has no support for Chromium's app-bound encryption (v20 cookies),
    which Chrome/Edge/Brave/Vivaldi/Opera all use from version 127 on. Those
    browsers are worth trying anyway on older installs, but the answer is almost
    always to export cookies to a file instead.
    """
    tried_list = list(tried)
    chromium = [name for name in tried_list if name in CHROMIUM_BROWSERS]
    print(
        "[auth] None of these browser cookie stores worked: " + ", ".join(tried_list),
        file=sys.stderr,
    )
    if chromium:
        print(
            f"[auth] Note: {', '.join(chromium)} encrypt cookies with app-bound "
            "encryption since Chromium 127, and gallery-dl cannot decrypt those. "
            "Use a cookies file instead (see README).",
            file=sys.stderr,
        )
    print(
        '[auth] Export cookies from a logged-in X session to ./cookies.json '
        '(Cookie-Editor: export the x.com entry as JSON), then rerun.',
        file=sys.stderr,
    )


def pick_browser_cookies(
    gallery_bin: Path,
    target_url: str,
    target_dir: Path,
    archive_file: Path,
    args: argparse.Namespace,
    env: dict[str, str],
    candidate_browsers: Iterable[str] | None = None,
) -> tuple[str | None, str | None]:
    base_command = build_gallery_dl_command(gallery_bin, target_url, target_dir, archive_file, args)

    print("[check] Testing whether the timeline is accessible without cookies...", file=sys.stderr)
    result = run_preflight(base_command, env)
    if result.returncode == 0:
        return None, None

    if not is_auth_required(result.stdout, result.returncode):
        return None, result.stdout

    print("[auth] X requires authenticated cookies for this profile. Trying browser sessions...", file=sys.stderr)

    candidates = list(candidate_browsers or AUTO_COOKIE_BROWSERS)
    for browser in candidates:
        print(f"[auth] Trying cookies from {browser}...", file=sys.stderr)
        browser_command = build_gallery_dl_command(
            gallery_bin,
            target_url,
            target_dir,
            archive_file,
            args,
            browser_override=browser,
        )
        browser_result = run_preflight(browser_command, env)
        if browser_result.returncode == 0:
            print(f"[auth] Using cookies from {browser}.", file=sys.stderr)
            return browser, None

    browser_cookie_hint(candidates)
    return None, result.stdout
