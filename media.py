"""Filesystem layout, stats, and the gallery-dl download archive."""



from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from .constants import (
    IMAGE_EXTENSIONS,
    IMAGES_SUBDIR,
    MEDIA_EXTENSIONS,
    SUMMARY_FILENAME,
    VIDEO_EXTENSIONS,
    VIDEOS_SUBDIR,
)





def format_bytes(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{num_bytes} B"

def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"

def archive_key_from_metadata(metadata: dict[str, object]) -> str:
    return (
        f"twitter{metadata['tweet_id']}_"
        f"{metadata.get('retweet_id', 0)}_"
        f"{metadata['num']}"
    )

def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1

def media_subdir_for_extension(extension: str) -> str | None:
    if extension in IMAGE_EXTENSIONS:
        return IMAGES_SUBDIR
    if extension in VIDEO_EXTENSIONS:
        return VIDEOS_SUBDIR
    return None

def reconcile_media_layout(root: Path, organize_media: bool) -> list[str]:
    if not root.exists():
        return []

    moved_paths: list[str] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        extension = path.suffix.lower()
        target_subdir = media_subdir_for_extension(extension)
        if target_subdir is None:
            continue

        destination_dir = root
        if organize_media:
            destination_dir = root / target_subdir
            if destination_dir in path.parents:
                continue
        elif path.parent == root:
            continue

        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = ensure_unique_path(destination_dir / path.name)
        shutil.move(str(path), str(destination))
        moved_paths.append(str(destination.relative_to(root)))

    for directory_name in (IMAGES_SUBDIR, VIDEOS_SUBDIR):
        directory = root / directory_name
        if directory.exists():
            try:
                directory.rmdir()
            except OSError:
                pass

    return moved_paths

def target_path_for_media(root: Path, metadata: dict[str, object], organize_media: bool) -> Path:
    extension = str(metadata["extension"]).lower()
    filename = f"{metadata['tweet_id']}_{metadata['num']}.{extension}"
    if organize_media:
        target_subdir = media_subdir_for_extension(f".{extension}")
        if target_subdir:
            return root / target_subdir / filename
    return root / filename

def collect_media_stats(root: Path) -> dict[str, object]:
    paths: set[str] = set()
    sizes: dict[str, int] = {}
    extension_breakdown: dict[str, int] = {}
    image_count = 0
    video_count = 0
    total_bytes = 0

    if root.exists():
        for path in root.rglob("*"):
            if not path.is_file() or path.name.startswith("."):
                continue
            if path.name == SUMMARY_FILENAME:
                continue

            extension = path.suffix.lower()
            if extension not in MEDIA_EXTENSIONS:
                continue

            relative_path = str(path.relative_to(root))
            size = path.stat().st_size
            paths.add(relative_path)
            sizes[relative_path] = size
            extension_breakdown[extension] = extension_breakdown.get(extension, 0) + 1
            total_bytes += size

            if extension in IMAGE_EXTENSIONS:
                image_count += 1
            elif extension in VIDEO_EXTENSIONS:
                video_count += 1

    return {
        "paths": paths,
        "sizes": sizes,
        "count": len(paths),
        "total_bytes": total_bytes,
        "image_count": image_count,
        "video_count": video_count,
        "extension_breakdown": dict(sorted(extension_breakdown.items())),
    }

def count_archive_entries(archive_file: Path) -> int | None:
    if not archive_file.exists():
        return None

    try:
        with sqlite3.connect(f"file:{archive_file}?mode=ro", uri=True) as connection:
            row = connection.execute("SELECT COUNT(*) FROM archive").fetchone()
            return int(row[0]) if row else 0
    except sqlite3.DatabaseError:
        try:
            with archive_file.open("r", encoding="utf-8") as handle:
                return sum(1 for _ in handle)
        except OSError:
            return None

def load_archive_keys(archive_file: Path) -> set[str]:
    if not archive_file.exists():
        return set()

    try:
        with sqlite3.connect(f"file:{archive_file}?mode=ro", uri=True) as connection:
            rows = connection.execute("SELECT entry FROM archive").fetchall()
            return {str(row[0]) for row in rows}
    except sqlite3.DatabaseError:
        try:
            with archive_file.open("r", encoding="utf-8") as handle:
                return {line.strip() for line in handle if line.strip()}
        except OSError:
            return set()

def insert_archive_entry(archive_file: Path, key: str) -> None:
    archive_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(archive_file, timeout=60) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS archive (entry TEXT PRIMARY KEY) WITHOUT ROWID"
        )
        connection.execute("INSERT OR IGNORE INTO archive (entry) VALUES (?)", (key,))
        connection.commit()
