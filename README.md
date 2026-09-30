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

X requires a logged-in session to read a profile timeline, so the tool needs your
X cookies. Export them to `cookies.json` and place it next to where you run the
command — it is picked up automatically.

### Exporting cookies with Cookie-Editor

1. Install the [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor) extension
   for your browser.
2. Log in to [x.com](https://x.com) in a normal tab and make sure you are signed in.
3. Click the Cookie-Editor icon in the toolbar.
4. Find the domain **`x.com`** in the list and expand it.
5. Confirm it contains **`auth_token`** and **`ct0`**. Those two are the ones that
   matter; without them X will reject the request.
6. Click **Export** (the download/arrow icon) in the Cookie-Editor window.
7. Choose **JSON** as the format and save the file.
8. Rename it to `cookies.json` and put it in the directory you run the command from.

On the first run the tool converts the JSON export to Netscape format automatically
and prints the path it wrote. Netscape `cookies.txt` files are also accepted as-is,
with or without `--cookies-file`.

```
[cookies] Using cookies.json by default.
[cookies] Converted JSON export to Netscape format: ...\cookies.netscape.json
```

### The cookie file is checked before downloading

Every cookie file is validated up front, so a stale export fails in under a second
instead of after a slow run that downloads nothing:

- **Missing or expired `auth_token`** — an error. X cannot be read without it, and
  the run stops with exit code 16 before any request is made. No converted file is
  written.
- **Missing or expired `ct0`** — a warning only. gallery-dl generates a `ct0` when
  one is absent, so this is not fatal, but X may reject a generated one. A full
  x.com export is preferred.

Expiry is judged only when the export states it, so session cookies are never
falsely reported as expired.

### Reading cookies straight from a browser

`--cookies-browser` passes through to gallery-dl, but it does **not** work with
Chrome, Edge, Brave, Vivaldi or Opera 127 or newer: those browsers encrypt cookies
with app-bound encryption, which gallery-dl cannot decrypt. Expect it to fail on a
modern Chromium browser. Firefox still works. When it fails, the tool says so.

```powershell
python -m xmd elonmusk --cookies-browser firefox  # may work
python -m xmd elonmusk --cookies-browser edge     # likely fails, see the note
python -m xmd elonmusk --cookies-file my.txt       # explicit Netscape file
```

Cookies expire. When a run extracts nothing and reports no error, export a fresh
copy.

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
