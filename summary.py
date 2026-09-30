"""Per-profile run summaries written next to the downloads."""



from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from .constants import SUMMARY_FILENAME

from .media import count_archive_entries, format_bytes, format_duration





def derive_run_status(
    exit_code: int, new_media_files: int, failed_media_files: int, discovered_media_files: int = 0
) -> str:
    if exit_code == 0:
        # gallery-dl exits 0 even when it fetched nothing (e.g. auth-walled timeline),
        # so an empty discovery must not be reported as success.
        return "empty" if discovered_media_files == 0 else "success"
    if new_media_files > 0 and failed_media_files > 0:
        return "partial"
    return "error"

def resolve_cookie_source(args: argparse.Namespace, browser_override: str | None) -> str:
    if args.cookies_file:
        return str(args.cookies_file.expanduser().resolve())
    if browser_override or args.cookies_browser:
        return f"browser:{browser_override or args.cookies_browser}"
    return "auto"

def build_run_summary(
    *,
    handle: str,
    profile_url: str,
    target_url: str,
    target_dir: Path,
    archive_file: Path,
    args: argparse.Namespace,
    browser_override: str | None,
    started_at: datetime,
    finished_at: datetime,
    duration_seconds: float,
    exit_code: int,
    before_stats: dict[str, object],
    after_stats: dict[str, object],
    discovered_media_files: int,
    skipped_media_files: int,
    failed_downloads: list[dict[str, str]],
) -> tuple[dict[str, object], Path]:
    before_paths = before_stats["paths"]
    after_paths = after_stats["paths"]
    after_sizes = after_stats["sizes"]
    new_media_paths = sorted(after_paths - before_paths)
    new_media_bytes = sum(after_sizes[path] for path in new_media_paths)
    summary_path = target_dir / SUMMARY_FILENAME
    failed_media_files = len(failed_downloads)

    summary = {
        "status": derive_run_status(
            exit_code, len(new_media_paths), failed_media_files, discovered_media_files
        ),
        "exit_code": exit_code,
        "profile_handle": handle,
        "profile_input": args.profile,
        "profile_url": profile_url,
        "target_url": target_url,
        "output_dir": str(target_dir),
        "archive_file": str(archive_file),
        "summary_file": str(summary_path),
        "cookie_source": resolve_cookie_source(args, browser_override),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round(duration_seconds, 3),
        "duration_human": format_duration(duration_seconds),
        "discovered_media_files": discovered_media_files,
        "skipped_media_files": skipped_media_files,
        "new_media_files": len(new_media_paths),
        "new_media_bytes": new_media_bytes,
        "new_media_bytes_human": format_bytes(new_media_bytes),
        "new_media_paths": new_media_paths,
        "failed_media_files": failed_media_files,
        "failed_downloads": failed_downloads,
        "total_media_files": after_stats["count"],
        "total_media_bytes": after_stats["total_bytes"],
        "total_media_bytes_human": format_bytes(after_stats["total_bytes"]),
        "image_files": after_stats["image_count"],
        "video_files": after_stats["video_count"],
        "pre_existing_media_files": before_stats["count"],
        "archive_entries": count_archive_entries(archive_file),
        "extension_breakdown": after_stats["extension_breakdown"],
        "options": {
            "include_retweets": args.include_retweets,
            "include_quoted": args.include_quoted,
            "exclude_pinned": args.exclude_pinned,
            "write_info_json": args.write_info_json,
            "verify_auth": args.verify_auth,
            "concurrency": args.concurrency,
            "retries": args.retries,
            "timeout": args.timeout,
        },
    }
    return summary, summary_path

def write_summary_file(path: Path, summary: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")
