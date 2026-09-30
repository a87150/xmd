# xmd — download all media from X/Twitter profiles

A batch downloader for everything an X/Twitter user has posted: every image and every
video from their media timeline. Wraps [gallery-dl](https://github.com/mikf/gallery-dl)
and [yt-dlp](https://github.com/yt-dlp/yt-dlp), which it installs for you on first run.

## Quick start

```powershell
python -m xmd elonmusk
```

Handle forms all work: `elonmusk`, `@elonmusk`, `x.com/elonmusk`,
`https://x.com/elonmusk`.

## Authentication

X requires a logged-in session to read a profile timeline. Export cookies from a
browser where you are logged in to X, save them as `cookies.json` next to where you
run the command, and you are done — it is picked up automatically.

Both the JSON array format (most browser extensions) and Netscape `cookies.txt` work.
A JSON export is converted to Netscape automatically on first use.

The cookies you need are `auth_token` and `ct0`. If the tool reports that it found
no media, the cookies have expired: export a fresh copy.

Alternative sources:

```powershell
python -m xmd elonmusk --cookies-browser edge   # read cookies from a local browser
python -m xmd elonmusk --cookies-file my.txt    # explicit Netscape file
```

## Batch

Download many profiles in one run. A failure retries and then moves on; it never
stops the rest.

```powershell
python -m xmd elonmusk nasa nasa_chat
```

```powershell
python -m xmd --profiles-file users.txt
```

`users.txt` holds one profile per line; `#` starts a comment:

```
# space / science accounts
nasa
@esa
x.com/SpaceX
```

## Resume and retries

Every run is resumable. Each profile keeps `downloads/<handle>/.download-archive.txt`,
so re-running only fetches what is missing. If a batch is interrupted, run the same
command again and it picks up where it left off.

- `--retries` — attempts per media file (default 3)
- `--profile-retries` — attempts per profile in a batch (default 2)

## Output

```
downloads/
  elonmusk/
    images/
      1901234567890123456_1.jpg
    videos/
      1901234567890123457_1.mp4
    .download-archive.txt
    download-summary.json
```

Each profile writes a `download-summary.json` with counts, sizes, and failures.
`--no-organize-media` keeps files flat instead of splitting into `images/` and `videos/`.

## Useful options

| Option | Effect |
| --- | --- |
| `-o, --output-dir` | Base directory for downloads (default `downloads/`) |
| `--organize-media / --no-organize-media` | Split into `images/` and `videos/` |
| `--concurrency` | Parallel media downloads (default 3) |
| `--retries` | Attempts per media file (default 3) |
| `--profile-retries` | Attempts per profile in a batch (default 2) |
| `--include-retweets` | Include media from retweeted posts |
| `--include-quoted` | Include media from quoted posts |
| `--exclude-pinned` | Skip the pinned post |
| `--write-info-json` | Write per-media `.json` metadata |
| `--cache-file` | gallery-dl cache location (default `.gallery-dl-cache.sqlite3`) |
| `--verify-auth` | Check cookies before downloading (slower) |
| `--dry-run` | Print the gallery-dl command and exit |

Run `python -m xmd --help` for the full list.

## Troubleshooting

**`error: gallery-dl: ...`** — this is gallery-dl's real error, passed through
exactly as reported. The most common ones:

- `OperationalError: attempt to write a readonly database` — the cache database
  could not be written. The tool keeps its cache at
  `.gallery-dl-cache.sqlite3` in the working directory for this reason; if you
  overrode `--cache-file`, point it somewhere writable.
- `AuthRequired` — the cookies are missing or expired.

**`found no media for this profile`** — gallery-dl extracted nothing *and*
reported no error. Either the profile genuinely has no media, or X returned an
empty timeline. The tool exits with code 17 here rather than reporting success.

**`--cookies-browser` finds no database`** — the browser cookie store is locked
because the browser is running. Close it first.

## Project layout

The repository root is this directory. Clone it, then run from its parent so the
package is importable:

```
git clone https://github.com/a87150/xmd.git
cd .. && python -m xmd elonmusk
```

```
xmd/            <- repository root
  __main__.py    entry point for python -m xmd
  cli.py         argument parsing, batch driver, per-profile orchestration
  profile.py     handle/URL normalization
  cookies.py     cookie loading and JSON-to-Netscape conversion
  toolchain.py   locate or bootstrap gallery-dl and yt-dlp
  gallery.py     build and run download commands, auth preflight
  media.py       filesystem layout, stats, download archive
  summary.py     per-profile run summaries
  constants.py   shared constants
  selftest.py    self-check: python -m xmd.selftest
```

No third-party Python dependencies. The tool bootstraps its own `.venv` for
gallery-dl and yt-dlp. Both that virtualenv and `downloads/` live outside the
repository, next to it.

## Security

`cookies.json` contains a live X session token — treat it like a password. It is
listed in `.gitignore` and must never be committed.
