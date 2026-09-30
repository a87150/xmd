"""Argument parsing, batch driver, and per-profile orchestration."""



from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .constants import (
    AUTO_COOKIE_BROWSERS,
    DEFAULT_COOKIES_FILE,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_VENV_DIR,
    IMAGES_SUBDIR,
    VIDEOS_SUBDIR,
)

from .cookies import ensure_netscape_cookies

from .gallery import (
    build_gallery_dl_command,
    download_media_items,
    extract_media_items,
    is_auth_required,
    is_cookie_db_missing,
    pick_browser_cookies,
    quoted_command,
    run_preflight,
)

from .media import collect_media_stats, reconcile_media_layout

from .profile import normalize_profile

from .summary import build_run_summary, write_summary_file

from .toolchain import ensure_toolchain





def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number

def nonnegative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number

def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download all media from a Twitter/X profile using gallery-dl and yt-dlp. "
            "The script auto-installs the tools into a local .venv when needed."
        )
    )
    parser.add_argument(
        "profile",
        nargs="*",
        help=(
            "One or more Twitter/X profiles, as URL, @handle, or plain handle. "
            "Each one is downloaded in turn; a failure does not stop the rest."
        ),
    )
    parser.add_argument(
        "--profiles-file",
        type=Path,
        help=(
            "File with one profile per line ('#' starts a comment). "
            "Combined with the positional profiles."
        ),
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Base directory for downloads (default: %(default)s)",
    )
    parser.add_argument(
        "--archive-file",
        type=Path,
        help="Path to gallery-dl's download archive file",
    )
    cookie_group = parser.add_mutually_exclusive_group()
    cookie_group.add_argument(
        "--cookies-file",
        type=Path,
        help=(
            "Cookie file to pass to gallery-dl. JSON exports are converted "
            f"automatically. Defaults to ./{DEFAULT_COOKIES_FILE.name} when that file exists."
        ),
    )
    cookie_group.add_argument(
        "--cookies-browser",
        help=(
            "Pass-through for gallery-dl --cookies-from-browser, "
            'for example: "firefox" or "chrome:Default"'
        ),
    )
    parser.add_argument(
        "--cache-file",
        type=Path,
        help=(
            "Override gallery-dl's cache database path. Needed when the default "
            "location under the user profile is not writable."
        ),
    )
    parser.add_argument(
        "--venv-dir",
        type=Path,
        default=DEFAULT_VENV_DIR,
        help="Local virtualenv used for gallery-dl/yt-dlp if bootstrapping is needed",
    )
    parser.add_argument(
        "--organize-media",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Place media into images/ and videos/ subfolders (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="Fail instead of auto-installing gallery-dl and yt-dlp",
    )
    parser.add_argument(
        "--include-retweets",
        action="store_true",
        help="Also fetch media from retweets",
    )
    parser.add_argument(
        "--include-quoted",
        action="store_true",
        help="Also fetch media from quoted tweets",
    )
    parser.add_argument(
        "--exclude-pinned",
        action="store_true",
        help="Skip media from pinned tweets",
    )
    parser.add_argument(
        "--write-info-json",
        action="store_true",
        help="Write gallery-dl metadata sidecars next to downloaded media",
    )
    parser.add_argument(
        "--verify-auth",
        action="store_true",
        help=(
            "Preflight-check cookies before the real download. "
            "Useful for debugging cookie issues, but slower."
        ),
    )
    parser.add_argument(
        "--concurrency",
        type=positive_int,
        default=3,
        help="Number of media files to download at once (default: %(default)s)",
    )
    parser.add_argument(
        "--retries",
        type=positive_int,
        default=3,
        help="Attempts per media file before marking it failed (default: %(default)s)",
    )
    parser.add_argument(
        "--profile-retries",
        type=nonnegative_int,
        default=2,
        help=(
            "Attempts per profile before moving to the next one in a batch "
            "(default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=positive_int,
        default=60,
        help="Network timeout in seconds for media downloads (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the gallery-dl command that would run and exit",
    )
    return parser.parse_args(list(argv) if argv is not None else None)

def collect_profiles(args: argparse.Namespace) -> list[str]:
    """Merge positional profiles with --profiles-file, preserving order and dropping duplicates."""
    values = list(args.profile)

    if args.profiles_file:
        try:
            listed = args.profiles_file.expanduser().read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ValueError(f"Could not read --profiles-file: {exc}") from exc
        values.extend(
            line.split("#", 1)[0].strip() for line in listed if line.split("#", 1)[0].strip()
        )

    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        key = value.strip().lstrip("@").lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(value)
    return unique

def run_profile(
    args: argparse.Namespace,
    profile: str,
    gallery_bin: Path,
    ytdlp_bin: Path,
    env: dict[str, str],
) -> int:
    args.profile = profile

    try:
        handle, target_url = normalize_profile(profile)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    target_dir = args.output_dir.expanduser().resolve() / handle
    target_dir.mkdir(parents=True, exist_ok=True)
    initial_moves = reconcile_media_layout(target_dir, args.organize_media)
    if initial_moves:
        destination_label = f"{IMAGES_SUBDIR}/ and {VIDEOS_SUBDIR}/" if args.organize_media else "the root folder"
        print(
            f"[organize] moved {len(initial_moves)} existing media file(s) into {destination_label}",
            file=sys.stderr,
        )
    before_stats = collect_media_stats(target_dir)

    archive_file = (
        args.archive_file.expanduser().resolve()
        if args.archive_file
        else target_dir / ".download-archive.txt"
    )

    browser_override = None

    command = build_gallery_dl_command(
        gallery_bin,
        target_url,
        target_dir,
        archive_file,
        args,
        browser_override=browser_override,
    )

    browser_override = None
    preflight_error = None
    if args.cookies_browser and args.verify_auth:
        preflight_result = run_preflight(command, env)
        if preflight_result.returncode == 0:
            pass
        elif is_cookie_db_missing(preflight_result.stdout):
            print(
                f'[auth] Requested cookies from {args.cookies_browser}, but no readable cookie database was found.',
                file=sys.stderr,
            )
            print("[auth] Trying other browser sessions instead...", file=sys.stderr)
            candidates = tuple(
                browser for browser in AUTO_COOKIE_BROWSERS if browser != args.cookies_browser
            )
            browser_override, preflight_error = pick_browser_cookies(
                gallery_bin,
                target_url,
                target_dir,
                archive_file,
                args,
                env,
                candidate_browsers=candidates,
            )
            if preflight_error:
                print(
                    preflight_error,
                    end="" if preflight_error.endswith("\n") else "\n",
                    file=sys.stderr,
                )
                print(
                    "error: no working browser cookie session was found. "
                    "Log into X in one of Edge, Chrome, Brave, Safari, or Firefox, then rerun.",
                    file=sys.stderr,
                )
                return 16
            command = build_gallery_dl_command(
                gallery_bin,
                target_url,
                target_dir,
                archive_file,
                args,
                browser_override=browser_override,
            )
        else:
            print(
                preflight_result.stdout,
                end="" if preflight_result.stdout.endswith("\n") else "\n",
                file=sys.stderr,
            )
            print(
                f"error: cookies from {args.cookies_browser} were loaded, but X still rejected the request.",
                file=sys.stderr,
            )
            return preflight_result.returncode or 16
    elif args.cookies_browser:
        print(
            "[note] Skipping auth preflight because you provided --cookies-browser. "
            "Use --verify-auth if you want the extra check.",
            file=sys.stderr,
        )
    elif args.cookies_file and not args.verify_auth:
        print(
            "[note] Skipping auth preflight because you provided --cookies-file. "
            "Use --verify-auth if you want the extra check.",
            file=sys.stderr,
        )
    elif args.cookies_file and args.verify_auth:
        preflight_result = run_preflight(command, env)
        if preflight_result.returncode != 0:
            print(
                preflight_result.stdout,
                end="" if preflight_result.stdout.endswith("\n") else "\n",
                file=sys.stderr,
            )
            print("error: the provided cookies file did not unlock the timeline.", file=sys.stderr)
            return preflight_result.returncode or 16
    elif not args.cookies_file:
        print(
            "[note] X/Twitter often requires authenticated cookies for profile timeline scraping.",
            file=sys.stderr,
        )
        browser_override, preflight_error = pick_browser_cookies(
            gallery_bin,
            target_url,
            target_dir,
            archive_file,
            args,
            env,
        )
        if preflight_error:
            print(preflight_error, end="" if preflight_error.endswith("\n") else "\n", file=sys.stderr)
            print(
                'error: automatic cookie detection could not unlock the timeline. '
                'Rerun with --cookies-browser "firefox" or --cookies-file "/path/to/cookies.txt" '
                "from a browser where you're logged into X.",
                file=sys.stderr,
            )
            return 16

        command = build_gallery_dl_command(
            gallery_bin,
            target_url,
            target_dir,
            archive_file,
            args,
            browser_override=browser_override,
        )

    print(f"[download] {handle} -> {target_dir}", file=sys.stderr)
    print(f"[command] {quoted_command(command)}", file=sys.stderr)
    started_at = datetime.now().astimezone()
    started_timer = time.monotonic()

    try:
        items = extract_media_items(command, env)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    download_result = download_media_items(
        items,
        target_dir,
        archive_file,
        ytdlp_bin,
        args,
        browser_override,
    )
    download_exit_code = int(download_result["exit_code"])
    finished_at = datetime.now().astimezone()
    duration_seconds = time.monotonic() - started_timer
    moved_media = reconcile_media_layout(target_dir, args.organize_media)
    if moved_media:
        destination_label = f"{IMAGES_SUBDIR}/ and {VIDEOS_SUBDIR}/" if args.organize_media else "the root folder"
        print(
            f"[organize] moved {len(moved_media)} media file(s) into {destination_label}",
            file=sys.stderr,
        )
    after_stats = collect_media_stats(target_dir)
    summary, summary_path = build_run_summary(
        handle=handle,
        profile_url=f"https://x.com/{handle}",
        target_url=target_url,
        target_dir=target_dir,
        archive_file=archive_file,
        args=args,
        browser_override=browser_override,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        exit_code=download_exit_code,
        before_stats=before_stats,
        after_stats=after_stats,
        discovered_media_files=int(download_result["discovered"]),
        skipped_media_files=int(download_result["skipped"]),
        failed_downloads=list(download_result["failures"]),
    )

    write_summary_file(summary_path, summary)
    print(
        "[summary] "
        f"new={summary['new_media_files']} "
        f"total={summary['total_media_files']} "
        f"images={summary['image_files']} "
        f"videos={summary['video_files']} "
        f"new_size={summary['new_media_bytes_human']} "
        f"total_size={summary['total_media_bytes_human']} "
        f"duration={summary['duration_human']}",
        file=sys.stderr,
    )
    print(f"[summary-file] {summary_path}", file=sys.stderr)

    if download_exit_code != 0:
        print(f"error: downloader exited with status {download_exit_code}", file=sys.stderr)
        return download_exit_code

    if summary["status"] == "empty":
        print(
            "[done] Downloader found no media for this profile. The timeline is likely "
            "auth-walled: re-export fresh X cookies and pass them via --cookies-file.",
            file=sys.stderr,
        )
        return 17

    print("[done] Download completed.", file=sys.stderr)
    return 0

def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        profiles = collect_profiles(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not profiles:
        print("error: no profiles given.", file=sys.stderr)
        return 2

    # Cookie setup is shared by the whole batch, so do it once.
    if not args.cookies_file and not args.cookies_browser and DEFAULT_COOKIES_FILE.is_file():
        args.cookies_file = DEFAULT_COOKIES_FILE
        print(f"[cookies] Using {DEFAULT_COOKIES_FILE} by default.", file=sys.stderr)

    if args.cookies_file:
        resolved = args.cookies_file.expanduser().resolve()
        cookies_path = ensure_netscape_cookies(resolved)
        if cookies_path != resolved:
            print(f"[cookies] Converted JSON export to Netscape format: {cookies_path}", file=sys.stderr)
        args.cookies_file = cookies_path

    try:
        gallery_bin, ytdlp_bin = ensure_toolchain(args.venv_dir, args.skip_bootstrap)
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    env = os.environ.copy()
    venv_bin_dir = ytdlp_bin.parent
    env["PATH"] = f"{venv_bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["PYTHONWARNINGS"] = (
        f"{env['PYTHONWARNINGS']},ignore" if env.get("PYTHONWARNINGS") else "ignore"
    )

    if args.dry_run:
        for profile in profiles:
            try:
                _, target_url = normalize_profile(profile)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                continue
            target_dir = args.output_dir.expanduser().resolve() / normalize_profile(profile)[0]
            target_dir.mkdir(parents=True, exist_ok=True)
            command = build_gallery_dl_command(
                gallery_bin,
                target_url,
                target_dir,
                target_dir / ".download-archive.txt",
                args,
            )
            print(quoted_command(command))
        return 0

    print(f"[batch] {len(profiles)} profile(s), {args.profile_retries} retr(ies) each", file=sys.stderr)
    failures: list[str] = []

    for index, profile in enumerate(profiles, 1):
        print(f"\n[profile {index}/{len(profiles)}] {profile}", file=sys.stderr)
        exit_code = 1
        for attempt in range(1, args.profile_retries + 2):
            if attempt > 1:
                print(f"[retry] attempt {attempt}/{args.profile_retries + 1} for {profile}", file=sys.stderr)
            exit_code = run_profile(args, profile, gallery_bin, ytdlp_bin, env)
            if exit_code == 0:
                break
        if exit_code != 0:
            failures.append(profile)

    if failures:
        print(
            f"\n[batch] {len(failures)}/{len(profiles)} profile(s) failed: "
            + ", ".join(failures)
            + "\n[batch] Rerun the same command to resume; finished files are skipped.",
            file=sys.stderr,
        )
        return 1

    print(f"\n[batch] all {len(profiles)} profile(s) completed.", file=sys.stderr)
    return 0
