<div align="center">

# gogrepo_delta

**Build and maintain your own offline copy of your GOG.com game library.**

A community-maintained Python tool for cataloguing, downloading, verifying, importing,
backing up, and organizing GOG installers and bonus content.

[![Version](https://img.shields.io/badge/version-0.5.50-blue)](https://github.com/MarS301/gogrepo_delta)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-green)](LICENSE.md)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)](#requirements-and-installation)

</div>

`gogrepo_delta.py` is a standalone continuation and refactoring of
[gogrepoc](https://github.com/kalanyr/gogrepoc). It keeps a local manifest of your GOG
library and helps you maintain a dependable, verifiable local collection.

> [!IMPORTANT]
> This is an independent community project. It is not affiliated with, endorsed by, or
> supported by GOG.

> [!WARNING]
> **New token storage.** New logins save credentials in `gog-token.json`, encrypted by default with a
> password you choose. Encrypted mode requires the third-party `cryptography` package
> (`python -m pip install cryptography`). The password is requested once per process and is never stored.
>
> - **Unattended machines:** set `GOGREPO_TOKEN_MODE=plain` explicitly. This stores the token as readable
>   JSON and provides **no encryption**.
> - **Existing `gog-token.dat` files** are read only when `gog-token.json` is absent. Their contents are
>   migrated to the new file; the legacy file is never modified or deleted.
> - **Damaged file or wrong password:** the program reports the problem rather than silently using an
>   older token. At a terminal a wrong or empty password is asked for again (3 attempts); in a scheduled
>   task or a pipe there is one attempt. If the password is forgotten, delete `gog-token.json` and run `login` again.

## Project at a glance

| | |
| --- | --- |
| **Current version** | `v0.5.50` |
| **Python requirement** | Python 3.10 or newer (3.8 and 3.9 start with a warning; best effort, not tested) |
| **License** | GPL-3.0-or-later |
| **Main script** | `gogrepo_delta.py` |
| **Upstream project** | [kalanyr/gogrepoc](https://github.com/kalanyr/gogrepoc) |

## Table of contents

- [Features](#features)
- [Requirements and installation](#requirements-and-installation)
  - [Required dependencies](#required-dependencies)
  - [Optional dependencies](#optional-dependencies)
- [Quick start](#quick-start)
  - [1. Sign in to GOG](#1-sign-in-to-gog)
  - [2. Update the manifest](#2-update-the-manifest)
  - [3. Download games and extras](#3-download-games-and-extras)
  - [4. Verify your collection](#4-verify-your-collection)
  - [5. Keep the collection up to date](#5-keep-the-collection-up-to-date)
- [Commands](#commands)
  - [login](#login)
  - [update](#update)
  - [download](#download)
  - [verify](#verify)
  - [import](#import)
  - [backup](#backup)
  - [list](#list)
  - [export](#export)
  - [wishlist](#wishlist)
  - [clean](#clean)
  - [clear_partial_downloads](#clear_partial_downloads)
  - [trash](#trash)
  - [diagnostics](#diagnostics)
- [Selecting games by tag](#selecting-games-by-tag)
- [Operating system and language selection](#operating-system-and-language-selection)
- [Configuration](#configuration)
- [Files and data safety](#files-and-data-safety)
  - [Manifest format and recovery](#manifest-format-and-recovery)
- [Logging and exit codes](#logging-and-exit-codes)
- [Troubleshooting](#troubleshooting)
- [Credits and links](#credits-and-links)
- [Changelog](#changelog)

## Features

- Download GOG game installers, Galaxy installers, shared installers, and bonus content.
- Select games by ID or title, operating system, and language.
- Detect the computer's operating system and language automatically.
- Use English as a fallback when the detected language is unavailable (unless language selection is explicitly supplied).
- Resume interrupted downloads using verified chunks where checksum data is available.
- Retry incomplete chunk downloads using the configured retry count and delay.
- Recover fully downloaded provisional files left behind by an interrupted run, even when no new downloads are needed.
- Verify file sizes, MD5 checksums, and ZIP archive integrity.
- Import existing collections by matching MD5 checksums.
- Create incremental backups.
- Move files not represented in the manifest into an orphaned area, and optionally remove duplicates or obsolete files.
- Download cover and background artwork.
- Store game information, serial numbers, and available changelogs alongside the collection.
- Export the manifest to a spreadsheet-friendly CSV file.
- Save your GOG wishlist (with optional prices) and see what changed since the last run.
- Search and list games in the manifest.
- Configure command defaults, network behaviour, logging, and download performance.
- Write manifests safely using atomic file replacement and keep backup copies.
- Produce end-of-run summaries and meaningful exit codes for automation.

## Requirements and installation

### Required dependencies

- Python **3.10 or newer** (3.8 / 3.9: starts with a warning, best effort, not covered by the tests)
- `html5lib`
- `requests`
- `psutil`
- `cryptography` (for the default encrypted token storage; not needed with `GOGREPO_TOKEN_MODE=plain`)

Install the required packages:

```bash
python -m pip install html5lib requests psutil cryptography
```

Download `gogrepo_delta.py` into a working directory and run it with Python:

```bash
python gogrepo_delta.py --help
```

The script must be started with a Python interpreter; do not execute it as a shell script.

### Optional dependencies

- `html2text` (2015.6.21 or newer): converts downloaded GOG changelogs from HTML to readable text.

  ```bash
  python -m pip install html2text
  ```

- `blake3`: enables BLAKE3 checksums for `download` and `verify` (see [BLAKE3 checksums](#blake3-checksums)). Without it everything works as before, using MD5 only.

  ```bash
  python -m pip install blake3
  ```

- **Linux/Unix:** PyQt5 with QtDBus support can be used for desktop-session sleep inhibition where supported.
- **macOS:** PyObjC components, including CoreFoundation support, are used for macOS-specific power-management functionality.
- **Windows:** required Windows API calls use Python's built-in `ctypes` module.

## Quick start

Run the commands below from the directory in which you want the program's working files (manifest, token, log, and configuration) to live. The game files themselves can be stored elsewhere.

### 1. Sign in to GOG

```bash
python gogrepo_delta.py login
```

Enter your GOG username/email when prompted. If the password is not supplied as an argument, it is requested securely. You will then be asked to create a password that protects the saved token (see the notice above).

If automatic login is blocked by a CAPTCHA or a changed GOG login page, use browser login:

```bash
python gogrepo_delta.py login --browser
```

A browser sign-in page is opened (or its address is displayed). Sign in, then paste the resulting URL when prompted. The authentication token is stored locally in `gog-token.json`.

**Security:** Do not pass your password on the command line. Command-line passwords can be exposed through shell history and process listings; this form is deprecated.

### 2. Update the manifest

```bash
python gogrepo_delta.py update
```

This retrieves library information from GOG and updates `gog-manifest.dat`. The standard update checks new and updated games. The default operating system and language are detected from the current computer.

### 3. Download games and extras

```bash
python gogrepo_delta.py download
```

Downloads the files selected by the manifest and the current OS/language defaults. To use a different destination:

```bash
python gogrepo_delta.py download "/path/to/GOG games"
```

### 4. Verify your collection

```bash
python gogrepo_delta.py verify
```

The verifier checks file sizes, MD5 checksums, and ZIP integrity. By default, files that fail verification are cleaned out of the collection (not silently treated as valid).

### 5. Keep the collection up to date

Run these commands periodically:

```bash
python gogrepo_delta.py update
python gogrepo_delta.py download
python gogrepo_delta.py verify
```

Updates and downloads are incremental. Interrupted downloads can be resumed where sufficient verified data is available. If a run is interrupted after a file has finished downloading but before it is moved out of `!downloading/!provisional`, the next run recovers that completed file even if there are no other downloads to perform.

## Commands

Every command supports `-h` or `--help`. Both the original single-dash long options (`-skipos`) and GNU-style double-dash options (`--skipos`) are accepted.

| Command | Purpose |
| --- | --- |
| `login` | Authenticate with GOG and save a local token. |
| `update` | Fetch library metadata and update the manifest. |
| `download` | Download installers and extras listed in the manifest. |
| `verify` | Check downloaded files against manifest data. |
| `import` | Import existing files by matching MD5 checksums. |
| `backup` | Create an incremental copy of a collection. |
| `list` | List or search games in the manifest. |
| `export` | Export manifest entries to CSV. |
| `wishlist` | Save the GOG wishlist and show what changed since the last run. |
| `clean` | Move files unknown to the manifest into `!orphaned`. |
| `clear_partial_downloads` | Remove incomplete download files. |
| `trash` | Permanently remove selected orphaned/duplicate files. |
| `diagnostics` | Generate diagnostic information for troubleshooting. |

### `login`

```bash
python gogrepo_delta.py login
python gogrepo_delta.py login --browser
```

Options:
- `username` (optional): GOG username or email.
- `password` (optional, deprecated): avoid supplying this; otherwise it may be exposed in shell history and process listings.
- `--browser`: use browser-based sign-in. Username and password arguments are ignored with a warning.

### `update`

```bash
python gogrepo_delta.py update
python gogrepo_delta.py update --full
python gogrepo_delta.py update --ids game_id another_game_id
```

Useful options:
- `--standard`: update new and updated games (default unless `--ids` is used).
- `--skipknown`: only update games not already in the manifest.
- `--updateonly`: only update games GOG marks as updated.
- `--full`: update all games in the account.
- `--ids ID ...` / `--skipids ID ...`: include or exclude selected games.
- `--tags TAG ...` / `--skiptags TAG ...`: include or exclude games by the tags of your GOG library (see [Selecting games by tag](#selecting-games-by-tag)).
- `--os OS ...` / `--skipos OS ...`: select or exclude operating systems.
- `--lang LANG ...` / `--skiplang LANG ...`: select or exclude languages.
- `--skiphidden`: skip games marked as hidden.
- `--resumemode {noresume,resume,onlyresume}`: control update resuming (default: `resume`).
- `--strictverify`: clear a previous verified state unless the MD5 matches.
- `--strictdupe`: use stricter duplicate matching when MD5 data is missing.
- `--lenientdownloadsupdate`: do not mark installers for update solely because their update timestamp changed when MD5 data is unavailable or differs.
- `--strictextrasupdate`: mark extras for update when their timestamps change, even if name and size match.
- `--md5xmls`: download available MD5 XML files.
- `--nochangelogs`: do not save game changelogs.
- `--diagnostic`: perform more exhaustive GOG data checks (slower and more verbose).
- `--wait HOURS`: wait before starting.
- `--installers {standalone,both}`: legacy installer selection option (deprecated).

### `download`

```bash
python gogrepo_delta.py download
python gogrepo_delta.py download "/path/to/GOG games" --dryrun
python gogrepo_delta.py download --ids game_id
```

Useful options:
- `--dryrun`: show what would be downloaded without downloading.
- `--ids ID ...` / `--skipids ID ...`: include or exclude games.
- `--tags TAG ...` / `--skiptags TAG ...`: include or exclude games by tag.
- `--os OS ...` / `--skipos OS ...`: select or exclude operating systems.
- `--lang LANG ...` / `--skiplang LANG ...`: select or exclude languages.
- `--skipextras`: skip bonus content.
- `--skipgames`: skip game installers (deprecated).
- `--skipgalaxy`, `--skipstandalone`, `--skipshared`: skip the respective installer groups (legacy/deprecated options).
- `--skipfiles FILE ...`: skip filenames or glob patterns.
- `--covers`: download cover images.
- `--backgrounds`: download background images.
- `--nocleanimages`: delete old artwork instead of cleaning it up.
- `--downloadlimit MB`: approximate download limit in megabytes.
- `--skippreallocation`: do not preallocate disk space.
- `--wait HOURS`: wait before starting.

### `verify`

```bash
python gogrepo_delta.py verify
python gogrepo_delta.py verify "/path/to/GOG games" --forceverify
```

Useful options:
- `--forceverify`: also verify files unchanged since their last successful verification.
- `--skipmd5`, `--skipsize`, `--skipzip`: skip the corresponding check.
- `--noblake3`: do not record or compare BLAKE3 checksums (see below). Also accepted by `download`.
- `--delete`: permanently delete files that fail integrity checks.
- `--noclean`: leave files that fail integrity checks in place.
- `--clean`: deprecated; cleaning is already the default.
- `--ids ID ...` / `--skipids ID ...`: include or exclude games.
- `--tags TAG ...` / `--skiptags TAG ...`: include or exclude games by tag.
- `--os OS ...` / `--skipos OS ...`: select or exclude operating systems.
- `--lang LANG ...` / `--skiplang LANG ...`: select or exclude languages.
- `--skipfiles FILE ...`: skip filenames or glob patterns.
- `--skipextras`, `--skipgames`, `--skipgalaxy`, `--skipstandalone`, `--skipshared`: limit the file types checked.
- `--highmemory`: use memory for multipart ZIP testing; at least 50 GB of available memory is recommended.
- `--lowtmpspace`: skip multipart ZIP tests when temporary disk space is insufficient.

**Exit status:** `verify` returns `1` if it finds any problem, including missing files.

#### BLAKE3 checksums

GOG publishes only MD5 checksums, so BLAKE3 cannot be compared with anything from GOG. Instead it is a **local fingerprint** kept in the manifest (field `blake3`), which needs the optional `blake3` package:

- **`download` records it right after a file has arrived** (v0.5.42). The file is hashed once, in its download thread, and kept only if its content is confirmed (see below). `verify` then needs no first pass for it. A file you already had, or one downloaded without the package, gets its BLAKE3 the first time it passes `verify` ("trust on first verify"); both hashes are computed in the same read pass.
- A later full check (`verify --forceverify`) compares only the recorded BLAKE3, which detects any change since the file last passed (for example bit rot) and is faster on fast disks. If the BLAKE3 differs and the MD5 is known, the MD5 decides: a mismatch is reported, a match means the stored BLAKE3 was stale and is refreshed.
- Files verified with an older version have no recorded BLAKE3 yet: run `verify --forceverify` once to record them.
- A BLAKE3 is recorded only for content that was actually confirmed (MD5 match, or for file types without MD5 a known size that matched). `--skipmd5` records nothing for files that have an MD5. After a download, a file whose MD5 in the manifest does not match what arrived gets no BLAKE3 and a warning (the download is kept; `verify` will report it). A file that is downloaded again because it changed never keeps the BLAKE3 of its old content.
- Use `--noblake3` (or `noblake3 = true` under `[download]` / `[verify]` in the config file) to switch the feature off. Without the package, `download` and `verify` say so once and behave as before. A `download --dryrun` hashes nothing.

### `import`

```bash
python gogrepo_delta.py import "/old/GOG collection" "/new/GOG collection"
```

Files are imported only when their MD5 checksums match manifest entries.

Options include `--ids ID ...`, `--skipids ID ...`, `--tags TAG ...`, `--skiptags TAG ...`, `--os OS ...`, `--skipos OS ...`, `--lang LANG ...`, `--skiplang LANG ...`, `--skipgalaxy`, `--skipstandalone`, and `--skipshared`.

### `backup`

```bash
python gogrepo_delta.py backup "/path/to/source" "/path/to/backup"
```

Creates an incremental backup by copying known files from the source collection to the destination.

Options include `--ids ID ...`, `--skipids ID ...`, `--tags TAG ...`, `--skiptags TAG ...`, `--os OS ...`, `--skipos OS ...`, `--lang LANG ...`, `--skiplang LANG ...`, `--skipextras`, `--skipgames`, `--skipgalaxy`, `--skipstandalone`, and `--skipshared`.

### `list`

```bash
python gogrepo_delta.py list
python gogrepo_delta.py list witcher
python gogrepo_delta.py list --format ids
```

Search terms are matched against game IDs, titles, and names; all supplied words must match, in any order. Put search words before options.

- `--format table`: readable table output (default).
- `--format ids`: one game title/ID per line for use in scripts.
- `--os OS ...`, `--skipos OS ...`, `--lang LANG ...`, `--skiplang LANG ...`: filter the listed games. By default `list` shows all systems and languages (it does not use the computer's defaults), but values from the config file apply.

If nothing is found, `list` says why and exits with `1`: either no game matches the words (with suggestions), or games match but none has files for the chosen operating system / language (the message names the games and the filter in use, which may come from the config file).

### `export`

```bash
python gogrepo_delta.py export
python gogrepo_delta.py export --output my-library.csv
python gogrepo_delta.py export --savedir "/path/to/GOG games"
```

Exports one CSV row per manifest file. The spreadsheet includes game ID/title, folder, file type, filename, OS, language, version, size, MD5, and update information. `--savedir DIR` adds an on-disk status column.

- `--output FILE`: output path (default: `gog-library.csv`).
- `--delimiter CHAR`: set the CSV separator. By default, the separator is selected for common spreadsheet locale conventions.

The CSV is UTF-8 with a byte-order mark (BOM) to improve compatibility with spreadsheet applications.

### `wishlist`

```bash
python gogrepo_delta.py wishlist
python gogrepo_delta.py wishlist --prices --country DE
python gogrepo_delta.py wishlist --prices --country DE --currency EUR --csv wishlist.csv
python gogrepo_delta.py wishlist --prices --country DE --csv        # writes gog-wishlist.csv
```

Saves the games on your GOG wishlist to `gog-wishlist.json` and says what changed since the last run: games that were added, games that were removed (marked "now in your library" if they are in the manifest), and, with `--prices`, games that became cheaper or dearer. **Nothing is downloaded**: GOG only provides installers for games you own.

The title, release date and store link of a game are fetched once and kept in the file, so later runs only ask GOG about new games. Requires `login` (the wishlist belongs to your account).

- `--prices`: also fetch the price of every game (one more request per game). Games without a price in the store (delisted, unreleased, not sold in that country) simply have none.
- `--country CODE`: the two-letter country the prices are for, like `DE`, `GB` or `US` (default: `US`). `UK` is taken as `GB`; a country GOG does not accept for prices is reported once and stops the price requests.
- `--currency CODE`: GOG gives one price per currency for a country (for example EUR and USD for `DE`); by default the first one is used.
- `--output FILE`: where to save the wishlist and what the next run compares with (default: `gog-wishlist.json`).
- `--csv [FILE]`: also write a spreadsheet (without a file name: `gog-wishlist.csv`) with title, release date (always as `2026-11-05`), store link, "in library", regular price, price, discount and promotion. `--delimiter CHAR` works as for `export`; with `;` the prices use decimal commas. The date is ISO on purpose: a spreadsheet reads a date in the order of your computer's language (`11/05/2026` becomes 11 May on a German Excel, and `06/23/2026` stays text), while `2026-11-05` is understood everywhere and then shown the local way.

If the CSV file is open in another program (on Windows, Excel locks it), the command says so before it fetches anything ("please close it and run the command again") and fails with exit status `1`; the CSV is written before the saved list is updated, so a later run still reports the changes.

The wishlist and price addresses are not officially documented by GOG and could change; if GOG answers with something unexpected, the command says so and fails with exit status `1`. Prices are rounded to what GOG reports in cents.

### `clean`

```bash
python gogrepo_delta.py clean "/path/to/GOG games" --dryrun
```

Moves files not known to the manifest into the `!orphaned` directory. Use `--dryrun` to preview the operation.

### `clear_partial_downloads`

```bash
python gogrepo_delta.py clear_partial_downloads "/path/to/GOG games" --dryrun
```

Removes partial download files. Use `--dryrun` to preview the operation.

### `trash`

```bash
python gogrepo_delta.py trash "/path/to/GOG games" --dryrun
```

By default, `trash` removes strict duplicates of known game files, matching file size and MD5 checksum.

Options:
- `--dryrun`: preview what would be removed.
- `--installers`: also delete installer file types even when they are not duplicates.
- `--folders`: also delete orphaned game folders when a corresponding game folder exists.
- `--images`: also delete orphaned `!images` directories when a corresponding images directory exists.
- `--relaxed`: relax duplicate checks and deletion requirements; use with care.
- `--installersonly`: deprecated alias for `--installers`.

**Warning:** `trash` permanently deletes files. Always run it with `--dryrun` first and inspect the output.

### `diagnostics`

```bash
python gogrepo_delta.py diagnostics
python gogrepo_delta.py diagnostics --verbose
```

Generates diagnostic information intended for maintenance and troubleshooting. `--verbose` includes additional information.

## Selecting games by tag

`--tags` and `--skiptags` use the tags you made in your GOG library (for example "Favorites" or "NEXT TO PLAY"). They work with `update`, `download`, `verify`, `import` and `backup`:

```bash
python gogrepo_delta.py update
python gogrepo_delta.py download --tags Favorites
python gogrepo_delta.py verify --tags "NEXT TO PLAY" Completed --skiptags Abandoned
```

- `update` reads your tags from GOG and stores their names in the manifest (`tag_names`). It refreshes them for every game on each run, so run `update` after you change tags on GOG. The other commands read the tags from the manifest and stop with a message if it has no tag data yet.
- A game matches if it has **any** of the tags given. Case, accents and punctuation do not matter. A tag with spaces must be in quotes.
- `--tags` together with `--ids` means the games that are in both. `--skiptags` always wins.
- A tag that no game has is an error (the message lists the tags that exist). If nothing is left to do, the command stops instead of running on all games.
- `update --tags` limits what is fetched but keeps the usual rule of what counts (new and updated games; add `--full` for all of them). Like `--ids`, a tag-limited update never removes games from the manifest.

## Operating system and language selection

For `update`, `download`, `verify`, `import`, and `backup`, the default selection is the current computer's operating system and detected language. If detection fails or the detected value is not offered by GOG, the script falls back to Windows and English.

- Use `--os windows linux mac` to explicitly select operating systems.
- Use `--lang en de` to explicitly select languages.
- Use `--skipos` and `--skiplang` to exclude values instead.
- The include and exclude forms for the same dimension are mutually exclusive.

When the language is selected automatically and is not English, English is used as a fallback **per game, file group, and operating system** if the preferred language is unavailable. An explicit `--lang` or `--skiplang` selection disables this automatic fallback. For example, a German default can select German Windows installers and English Linux installers when no German Linux installer exists.

**Manifest note:** an update replaces the stored file information for each game it fetches. If you need multiple OS/language variants, specify them explicitly (for example, `--os windows linux --lang en de`). A plain update can replace other variants previously stored for an updated game; files already on disk are not automatically deleted.

Before a new update starts, the program compares the manifest with the operating systems and languages the update will use. If the update would drop installer entries for other systems or languages, it **warns** (it does not stop): how many installer files of how many games would go and why, that `clean` would then take the files on disk for orphans and move them to `!orphaned`, and that a later update that includes them again adds the entries back as new ones (`download` then checks them again and fetches only what is not right). To avoid it, give all the systems and languages you use with `--os` / `--lang`, or put them in the config file. An update without `--full` says "up to N" because only new and updated games are fetched.

## Configuration

On first run, the program creates `gogrepo_delta.cfg` in the current working directory. Set `GOGREPO_DELTA_CONFIG` to use a different configuration file.

The INI-style file has these sections:

- `[settings]`: internal settings such as HTTP timeouts/retries, download chunk size, thread count, logging limits, progress interval, and save thresholds.
- `[common]`: command-line defaults shared by commands.
- Command sections such as `[update]`, `[download]`, and `[verify]`: command-specific defaults.

Configuration precedence (highest first):

1. Options explicitly supplied on the command line.
2. The relevant command section.
3. `[common]`.
4. Built-in defaults.

Boolean settings accept `true`/`yes`/`on`/`1` and `false`/`no`/`off`/`0`. Lists must be separated by commas or written one item per line; spaces and semicolons are not list separators. Section names and `os` and `lang` values must be lowercase. Option names may use any case. Game IDs and names are matched without regard to case. Empty values use the built-in default. Unknown keys produce warnings; invalid values stop the command with an explanatory message. The program does not overwrite an existing configuration file. These rules are also described in the header of newly generated configuration files; existing files are left unchanged.

Example:

```ini
[common]
# Apply to commands that support these options
os = windows
lang = en

[settings]
download_threads = 4
http_timeout = 30
```

Use a different configuration file:

```bash
# Linux / macOS
export GOGREPO_DELTA_CONFIG="/path/to/my-config.cfg"

# Windows Command Prompt
set GOGREPO_DELTA_CONFIG=C:\path\to\my-config.cfg
```

Login credentials are never read from the configuration file.

## Files and data safety

The program keeps its state files in the current working directory (unless configured otherwise):

| File | Purpose |
| --- | --- |
| `gogrepo_delta.cfg` | Configuration and command defaults. |
| `gog-token.json` | Saved GOG authentication token (encrypted by default). Treat it as a credential. |
| `gog-token.dat` | Legacy token file from older versions. Read-only; never modified or deleted. |
| `gog-manifest.dat` | Main library manifest (JSON by default). |
| `gog-manifest.dat.bak` | Previous manifest version. |
| `gog-manifest.dat.legacy` | One-time preservation of the old manifest format during migration. |
| `gog-resume-manifest.dat` | State used to resume interrupted updates. |
| `gog-config.dat` | Internal GOG configuration data. |
| `gogrepo.log` | Log file. |
| `gog-library.csv` | Default CSV export output. |
| `gog-wishlist.json` | Default output of `wishlist`; the next run compares with it. |
| `gog-wishlist.csv` | Default CSV output of `wishlist --csv`. |

### Manifest format and recovery

Older manifests without stored `api_downlink` information remain supported. If chunk information cannot be retrieved for a file (for example, when an older manifest is used with a signed download URL), that file is downloaded without chunk verification rather than failing because the chunk information is unavailable.

The manifest and resume manifest are written as indented JSON by default. Existing legacy-format manifests remain readable. To write the old format:

```bash
python gogrepo_delta.py update --manifestformat legacy
```

JSON saves are checked by reading the data back. If it cannot be represented without changing its meaning, the old format is used for that save. Saves are atomic; the previous manifest is retained as `.bak`.

If the manifest is missing or damaged and a backup exists, the program offers an interactive restore. A damaged manifest is preserved with a `.damaged` suffix. In non-interactive runs, it stops rather than asking an unanswered question or silently treating a damaged manifest as an empty library. A first run with neither manifest nor backup is normal.

**Back up `gog-token.json` securely** if you want to preserve the login session, and do not share it in bug reports.

## Logging and exit codes

Logs are written to `gogrepo.log`, with timestamps and severity levels. Common options:

- `--nolog`: disable file logging.
- `--debug`: enable additional debug output.
- Log rotation is configurable in `gogrepo_delta.cfg`.

The first line of every run in the log file is the version of the program, with the Python and the system it ran on (for example `gogrepo_delta.py version 0.5.50 (Python 3.14.0, Windows-11-...)`). It is written to the file only, not to the console, and not with `--nolog`.

At the end of a command, the program reports a summary of completed work and lists failures with reasons. `files downloaded` counts the files of which data was fetched, with the amount that really came from GOG; `files verified in place (nothing downloaded)` counts files that were marked for change but were already right on the disk, chunk by chunk, and needed no data. Completed files recovered from an earlier interrupted run are included in the recovery count.

When a chunk download is incomplete, the chunk-verification retry loop waits for `http_retry_delay` before each retry, except after the final attempt. The wait occurs outside the download job lock, so other downloads can proceed. With the default settings, retry delays can add up to 20 seconds (4 retries × 5 seconds) before the download gives up.

**Exit status:**

- `0`: command completed without reported failures.
- `1`: one or more failures occurred, a fatal error occurred, or the run was interrupted.

A command can therefore complete most of its work and still return `1`. This is intentional and useful for scripts and scheduled jobs.

## Troubleshooting

- Run `python gogrepo_delta.py --help` or `python gogrepo_delta.py COMMAND --help` for the exact options accepted by your copy.
- Run `diagnostics`; add `--verbose` for additional details.
- Check `gogrepo.log` for timestamped error messages.
- If a manifest cannot be read, preserve the `.bak` and `.damaged` files before attempting manual recovery.
- If login encounters a CAPTCHA or GOG changes its login page, try `login --browser`.
- For scheduled tasks, remember that recovery prompts require an interactive terminal; unattended runs stop safely instead of waiting for input.

## Credits and links

- Current repository: [MarS301/gogrepo_delta](https://github.com/MarS301/gogrepo_delta)
- Original projects: `eddie3` and `kalanyr`
- Current version contributors: `MarS301`, `claude.ai` and `chatgpt`
- GOG: [https://www.gog.com/](https://www.gog.com/)

See [CHANGELOG.md](CHANGELOG.md) for the changes documented for this version.

## Changelog

Every change, newest first, the known issues and the rule for the version number (`0.5.N`, where N is the number of the newest entry) are in [CHANGELOG.md](CHANGELOG.md).

---

<div align="center">

**Preserve your library. Verify your files. Keep control of your collection.**

</div>
