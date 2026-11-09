# Changelog

Every change to `gogrepo_delta.py`, newest first. Below it: how the versions work, and the known issues. This file is the former
"REFACTORING NOTES" block at the top of the script, moved here in full; the script now only points to it.

The goal of the refactoring was to keep behaviour. The only intended differences are listed explicitly, marked **DIFFERENCE**. Places in the
code that were changed for an entry may carry a "Refactoring" comment or docstring.

## How the version works

- The version is `0.5.N`, where **N is the number of the newest entry** below. Every new entry raises the version, so the entry number and
  the patch number always match. A test (`tests/test_config.py`) reads this file and fails if they do not.
- Entries 1-23 were made before this rule existed. Their headings say "Entry N" and do not name a version; the rule starts with entry 24.
- Small corrections that are not worth an entry (a spelling in the credits, say) do not change the version.
- The script stays one file, by choice.

## Known issues (not fixed yet)

- Unreachable code is kept as it was: the `AttributeError` defaults for `folder_name`, `galaxyDownloads` and `sharedDownloads` in `cmd_download`
  (`handle_game_renames` sets them first), the `SSLError` branch in `_download_ioloop` (an `SSLError` is a `ConnectionError` and is caught by the
  branch before it) and the `os.makedirs(dest_dir)` in `_prepare_download_file`.
- `HTTP_FETCH_DELAY` is defined but not used anywhere, so it is not a setting in the config file.
- `update_self()` is not connected to any command; it reads the releases of the repository named in `REPO_HOME_URL`.
- In the combined "No MD5 data was available" warning produced while downloading (several worker threads), the order of the file names can
  differ from run to run. Only the order differs.
- A language group that contains only a patch counts as "has your language" for that system (edge case, not handled).
- A legacy-format manifest that holds valid data of the wrong type (a bare number, say) is accepted by the loader and fails later; damaged files
  are handled (found in the review of entry 30).
- Reading the legacy manifest format is 3-4 times slower than it was with `eval` (0.7 s for a 1.2 MB file, 12 s for 23 MB); the JSON format, which is
  the default, is not affected.
- Saving the legacy manifest format still re-formats the whole manifest on every save (the cost grows with the library); it is not the default.
- A save that is killed hard (power loss, task kill) between creating and renaming its temporary file leaves a randomly named `*.tmp` file behind;
  nothing removes it later (entry 30). They are ignored by `.gitignore`.

## 0.5.51 - 08.11.2026 - Safer and less redundant MD5 XML cleanup

- **Do not discard MD5 XML when GOG metadata is incomplete.** During cleanup, a download or released extra with no filename can indicate a metadata-fetch failure. Existing XML files in that affected language/download folder or extras folder are now retained instead of being treated as obsolete. Once all relevant entries have names again, normal stale-file cleanup resumes.
- **Remove redundant directory enumeration.** The download-language XML directory is now listed once (the old code listed it twice through nested loops). The language list is also built in one pass instead of repeating the same scan for each item.
- Existing named entries are still cleaned normally: stale XML is removed when the manifest has complete filename information, and expected XML files remain untouched.
- `tests/test_md5_cleanup.py`: regression coverage for preserving existing download and extra MD5 XML when names are unknown, and for normal cleanup when names are known.

DIFFERENCE: cleanup is deliberately more conservative when manifest metadata is incomplete; valid existing MD5 XML is no longer deleted on that evidence alone.

## 0.5.50 - 07.11.2026 - Failed game details remain pending in the resume manifest

- A game whose details could not be fetched or processed is no longer removed from the resume manifest. It remains pending, and `complete` stays false until every game has been processed successfully.
- A later `update` retries the pending game. The run reports how many games remain pending and tells the user to run `update` again.
- `tests/test_update_saves.py`: regression tests cover retaining a failed game, keeping the resume manifest incomplete, and retrying the game successfully on the next run.

DIFFERENCE: failed game-detail requests are retried on a later `update` instead of being silently discarded from resume state.

## 0.5.49 - 07.11.2026 - `wishlist`: the CSV always writes the release date as ISO (2026-11-05)

- **The date of the CSV is `YYYY-MM-DD` in every case.** The by-country formats of 0.5.45 are gone (`_DATE_FORMATS` and the `country` parameter of `format_release_date()` and `write_wishlist_csv()`): Excel reads a date in
  the order of the computer's language, so `11/05/2026` became 11 May on a German Excel while `06/23/2026` was left as text. `2026-11-05` is understood in every locale and then shown the local way. The day is
  the one in GOG's text (no time zone conversion); the saved JSON file keeps the original text.
- **`-country` is only for the prices** (default `US`; `UK` is taken as `GB`), as before. The extra text about the date format in the message after the CSV (0.5.48) is gone again.
- `tests/test_wishlist.py`: the date tests are for the ISO form, and one checks that the country still selects the prices and nothing else (53 tests).

DIFFERENCE: the release date column of the CSV is ISO instead of the format of the country.

## 0.5.48 - 07.11.2026 - `wishlist`: a CSV file that is open in Excel is reported instead of a traceback

- **A locked CSV file.** On Windows a spreadsheet program that has the file open makes writing it fail with `PermissionError`, which ended the run with a traceback (`fatal...`) after the saved list had been updated.
  Now `file_write_problem()` checks the CSV file first, before anything is fetched (opening for appending changes nothing in the file and a file that did not exist is not left behind), and the command says
  `cannot write gog-wishlist.csv (Permission denied). If the file is open in another program, for example Excel, please close it and run the command again.`, counts one failure (`csv: file cannot be written`) and exits with status 1.
- **The CSV is written before the saved list is updated.** If the file gets locked after the check, the same message appears and the saved list is left as it was, so the next run reports the same changes again instead of "no changes".
  A saved list (`-output`) that cannot be written is reported the same way instead of with a traceback.
- **The message after the CSV says which date format was used** (`dates as written in DE, like 31.12.2026`, or `dates as 2026-12-31 (give -country ...)` without a country), so it is visible why the dates look as they do.
- `tests/test_wishlist.py`: 7 new tests (54 in total).

DIFFERENCE: only the error handling of the `wishlist` files and the wording of one message.

## 0.5.47 - 07.11.2026 - `wishlist -csv` without a file name writes `gog-wishlist.csv`

- `-csv` takes an optional file name now (`nargs='?'`): `wishlist -csv` writes `gog-wishlist.csv` (`WISHLIST_CSV_FILENAME`), `wishlist -csv my.csv` writes `my.csv`, and without `-csv` no CSV file is written, as before.
  Another option after `-csv` is not taken as its file name (`wishlist -csv -prices`). A `csv = ...` entry of the configuration file works as before.
- `tests/test_wishlist.py`: 9 new tests (47 in total), among them how `-csv` and a `csv = ...` entry of the configuration file go together (the command line wins).

DIFFERENCE: `-csv` alone was an error ("expected one argument") and now works; nothing else changes.

## 0.5.46 - 07.11.2026 - A wrong token password is asked for again

- **A wrong password no longer ends the run with a traceback.** `_read_token_json` now asks for the password again (`Wrong password. Please try again (1 of 3).`), up to `TOKEN_PASSWORD_ATTEMPTS` (3) times, when the program is
  run from a terminal (`_can_prompt_again()`); in a scheduled task or a pipe there is one attempt, as before. The wrong password is forgotten, so it is never used twice, and the right one is kept for the rest of the run
  (saving the refreshed token does not ask again).
- **An empty password** is asked for again as well. It used to be stored as the password (`_TOKEN_PASSWORD = ''`), so a second call did not ask any more.
- **After the last attempt** the same `could not decrypt token file (wrong password or damaged file)` is raised, now as `TokenPasswordError` (a `ValueError`, so existing handlers still work); the top level logs it without a traceback,
  with the hint to delete `gog-token.json` and run `login` again if the password is forgotten, and exits with status 1.
- `tests/test_token_password.py`: 10 tests. (The top-level message in the `__main__` block is not covered by a test.)

DIFFERENCE: only the handling of a wrong or empty token password.

## 0.5.45 - 07.11.2026 - `wishlist`: release dates by country, `UK`, and an empty wishlist

- **Release date of the CSV by country.** `wishlist -country DE -csv ...` writes `23.06.2026` instead of GOG's `2026-06-23T18:59:00+0200`: `format_release_date()` uses the order and separators of the country
  (DE, AT, CH, PL, CZ ... `23.06.2026`; GB, FR, ES, IT, AU, BR ... `23/06/2026`; US, PH `06/23/2026`; NL `23-06-2026`; JP, CN, TW `2026/06/23`; KR, HU `2026. 06. 23.`) and ISO `2026-06-23` without a country or for a
  country that is not in the list. The day is the one in GOG's text (no time zone conversion). The saved JSON file keeps the original text.
- **`-country` has no default value any more** (it is still `US` for the prices): the dates are only written for a country that was given. A configuration file entry `country = ...` works as before.
- **`UK` is taken as `GB`** (`UK` is not an ISO code; GOG answers 400 Bad Request for it). **A country GOG refuses is not retried:** a 400 on the price request is reported once ("use the two-letter ISO code, for example GB"),
  counted as one failure, and the other prices are not requested; the wishlist is still saved. Before, the same request was repeated 4 times with 5 seconds in between, for every game. `request()` has a new
  parameter `no_retry_statuses` for this (statuses that are raised at once for that call only; the global `http_no_retry_codes` are unchanged).
- **An empty wishlist** is sent by GOG as `"wishlist": []`, not `{}`; it was refused with "the answer of GOG has no "wishlist" list". It is read as 0 games (games that were on the list before are reported as removed);
  a list of ids is accepted too.
- `tests/test_wishlist.py`: 38 tests (13 new).

DIFFERENCE: only the `wishlist` command and one new optional parameter of `request()`.

## 0.5.44 - 07.11.2026 - New command `wishlist`: save the GOG wishlist and see what changed

- **New:** `wishlist` saves the games on the wishlist of the logged-in account to `gog-wishlist.json` (`-output`) and reports what changed since the last run: added games, removed games
  (and which of them are now in the manifest), and, with `-prices`, games whose price went down or up. `-csv FILE` writes a spreadsheet (`-delimiter` as for `export`; with `;` the prices use
  decimal commas). Nothing is downloaded: wishlist games are not owned, and GOG gives installers only for owned games.
- **The addresses** (not documented by GOG): `embed.gog.com/user/wishlist.json` (`{"wishlist": {"<id>": true, ...}, "checksum": ...}`), `api.gog.com/products/<id>` for title, slug, release date and
  store link, and `api.gog.com/products/<id>/prices?countryCode=DE`, which lists one price per currency as `"<cents> <currency>"` strings (`"999 EUR"`). Prices are kept as integer cents
  (`parse_gog_money()`, `choose_price()`); `-country` (default `US`) and `-currency` (default: the first one listed) pick what is saved. The format of the first two was checked with real answers
  of an account; the details of `api.gog.com/products/<id>` (`title`, `slug`, `release_date`, `links.product_card`) are read defensively and every field is optional.
- **Details are fetched once** and kept in the file, so a later run only asks for new games (and for games whose details were not available before); prices are fetched for every game on each run with `-prices`.
  A game GOG has no details or price for (404) is kept without them and is not a failure; other request errors are failures (exit status 1). Without `-prices` the saved prices stay and are not reported as changes.
- It uses the normal `request()` (timeouts, retries, the token refresh) and writes the file atomically. A saved file that cannot be read means a first run, with a warning.
- `tests/test_wishlist.py`: 25 tests against a local fake GOG server that answers in the format of the real responses.

DIFFERENCE: a new command only; no existing command, manifest or option changes. **Not tested against the live service:** whether the token the program holds is accepted by `embed.gog.com/user/wishlist.json` (as it is by the other `embed.gog.com` calls) has to be
confirmed with a real run; if GOG answers with a login page, the command says so and suggests logging in again.

## 0.5.43 - 06.11.2026 - The PyObjC package to install is `pyobjc-framework-Cocoa`

- The macOS build in `build.yml` failed at "Install macOS-only dependencies" (`No matching distribution found for pyobjc-framework-CoreFoundation`): that package name does not
  exist. The `CoreFoundation` module (and, through its dependency `pyobjc-core`, the `objc` module) comes with **`pyobjc-framework-Cocoa`**, which `tests.yml` already used.
  `build.yml` now installs that one, with `python -m pip` like the other steps.
- The hint printed when PyObjC is missing (added in 0.5.40) named the wrong package too; it now says `python -m pip install pyobjc-framework-Cocoa`. The test for that warning checks the name.

DIFFERENCE: only a message and the CI file change.

## 0.5.42 - 06.11.2026 - `download` records the BLAKE3 of each file right after it arrived

- **New:** with the optional `blake3` package installed, `cmd_download` hashes every file that has arrived and stores the result in the `blake3` field of its manifest entry,
  so a `verify` that follows does not have to be the "first verify" for it. The hashing runs in the downloader thread that finished the file (`_download_blake3()`, called
  after the move to `!provisional`), so it overlaps with the other downloads and reads a file that is still in the disk cache; the value is written to the manifest by
  `_finish_provisional_downloads()` together with the flags it already resets, in the same single save. Files recovered from an earlier run (already in `!provisional`) are hashed there.
- **The same rule as `verify`: only confirmed content gets a baseline.** With an md5 in the manifest, md5 and BLAKE3 are computed in one read pass and the BLAKE3 is kept only if the md5
  matches (a mismatch logs a warning, keeps the download and records nothing; `verify` will report it). Without an md5 (types GOG gives no md5 for) the known size must match.
- **A re-downloaded file never keeps the BLAKE3 of its old content:** if new data came in and no new BLAKE3 could be recorded (no package, `-noblake3`, md5 mismatch), the old value is removed.
- New option `-noblake3` for `download` (also in the config file); without the package `download` says so once, like `verify` (not on a dry run, which hashes nothing).
  A failure while hashing only produces a warning; it never makes a download fail. `prev_verified` is untouched: only `verify` marks a file as verified.
- `tests/test_download_blake3.py`: 11 tests on 8 new scenarios of the download rig (`blake3_*`). The rig now patches `_blake3` to `None` unless a scenario asks for the stand-in, so the results do not depend on whether the package is installed on the machine.

DIFFERENCE: with `blake3` installed, `download` adds the field `blake3` to the manifest entries of the files it fetched and reads each finished file once more. Without the package, or with `-noblake3`, nothing changes except the one-line notice.

## 0.5.41 - 06.11.2026 - Less console output when many files are missing

- **`verify`: one line per game.** A game that was not downloaded (yet) printed one `missing file ...` warning per file, 99 lines for 14 games, and
  the same files were listed again in the run summary. Up to `MISSING_FILES_LISTED` (3) missing files of a game are still named; beyond that one line
  says `game: 6 of 6 files missing`, and the names go to the debug level (run with `-debug` to see them). Every missing file still counts as a failure (exit status, summary).
- **Grouped failure list in the run summary.** When there are more failures than `max_listed_failures` and all of them are files inside game folders, the summary
  shows one line per reason (`missing: 99 files in 14 games`) and the games with their number of files in a wrapped paragraph, instead of the first 40 file names and
  "and 59 more". A short list still names every file, and failures without a folder keep the old cut-off.
- `tests/test_failure_summary.py`: 9 tests.

DIFFERENCE: only the wording and amount of console / log output changes. No file is treated differently, and the counts, exit status and manifest are as before.

## 0.5.40 - 05.11.2026 - Review fixes: download hang, token timeout, root file system, partial info files, macOS without PyObjC, Python 3.8 / 3.9

- **Download threads could wait forever.** `_download_worker` asked `job.work.empty()` and then called `job.work.get()`. With several threads, two of them
  could both see one file left; the second waited in `get()` for a file that never came, and `cmd_download` waited for that thread. It now takes files with
  `get_nowait()` and stops on `queue.Empty`.
- **The token refresh had no timeout** (`renew_token` called `session.get` without `timeout=`); a connection that stalled held `token_lock`, so every thread
  waited. It now uses `http_timeout`, like every other request.
- **An expired login in a download thread.** `renew_token` ended with `sys.exit(1)`; in a worker thread that only ended the thread, and the run reported
  "a download thread stopped unexpectedly". It now raises `AuthExpired`, a `SystemExit` subclass (so in the main thread nothing changes: exit status 1, and no
  `except Exception` can swallow it). A worker catches it, marks its file as failed with "login expired, run the login command again", and sets
  `job.abort`, so the other workers take no new files; the files that were not started are reported with the same reason.
- **`get_fs_type` never tried the root mount `/`**, so a folder on the root file system was "unknown" and was not preallocated (containers, one-partition installs).
- **`ConditionalWriter` wrote its buffer even when the `with` body raised**, which could leave an incomplete `!info.txt`, `!serial.txt` or MD5 XML. It writes
  nothing then. A changed existing file is now replaced atomically (`atomic_write_text`, permissions kept; in place as before if the folder is read-only).
- **macOS without PyObjC.** `CoreFoundation` and `objc` were imported unconditionally, although the README lists PyObjC as optional. They are imported by
  `_import_macos_modules()`; without them the `Wakelock` is skipped with one warning and the program runs.
- **Python 3.8 and 3.9.** The check exited below 3.10, so the `specialPy3 = [3,8]` branch was dead. Now only versions below 3.8 stop; 3.8 and 3.9 print a
  warning and carry on (`check_python_version()`). The one call that needed 3.10, `glob.glob(..., root_dir=...)` in the split-zip test of `verify`, is replaced by
  `_multi_zip_parts()`. The syntax was checked for 3.8, but there is **no 3.8 / 3.9 in the test matrix**: they are best effort.
- `tests/test_review_fixes.py`: 24 tests, one or more for each point above. (`assertNoLogs` in `tests/test_run_summary.py` needs 3.10; the tests themselves still
  need 3.10.)

DIFFERENCE: an expired login inside a download thread now stops the download run with "login expired" failures instead of a silent thread death; Python 3.8 and 3.9 start
with a warning instead of exiting. Everything else only removes a hang, a wrong "unknown" or a corrupt write.

## 0.5.39 - 04.11.2026 - `-tags` and `-skiptags`: select games by the tags of your GOG library

- The tags are the ones you made in your GOG library (for example "Favorites", "NEXT TO PLAY"). GOG sends them with the product list: every product has a list of tag ids, and the whole answer has the list of `{id, name}`. `update` now stores the **names** in the new field `tag_names` of every game in the manifest. Matching ignores case, accents, punctuation and spacing (`-tags "next to play"` finds `NEXT TO PLAY`); a game matches if it has **any** of the tags given.
- New options `-tags TAG ...` and `-skiptags TAG ...` for `update`, `download`, `verify`, `import` and `backup` (also settings in the config file). They combine with each other and with `-ids` / `-skipids`: `-tags` with `-ids` means the games that are in both; `-skiptags` always wins. A tag with spaces must be in quotes; if the words of one tag were typed without quotes, the message says so.
- `download`, `verify`, `import` and `backup` read the tags from the manifest: the options are turned into ids before the command runs (`apply_tag_options()`), so those commands needed no change. The selection can never fall through as "all games": if nothing is left, or the manifest has no tag data yet (run `update` once), the command stops with a message. A tag that no game has is an error and fails the run, with a list of the tags that exist.
- `update -tags` / `-skiptags` limit what is fetched, like `-ids` does, but keep the normal rule for what counts (new and updated games; add `-full` for all of them). Like `-ids`, a tag-limited update never removes games from the manifest. A tag that does not exist in your library is reported at the end of the run and fails it; a tag that exists but has no games is not an error.
- Every `update` that reads the product list also refreshes `tag_names` of the games that it does not fetch again (the list is read anyway; no extra requests), and saves the manifest if a tag changed. So a tag change on GOG reaches the manifest with the next `update`, even a plain one.
- The tag data was checked against the documented format of the GOG product list (`tags` with `id`, `name` at the top and a list per product). The format of the per-product list was not visible in an example with data, so ids, `{id, name}` entries and unknown ids are all handled; an id without a known name is kept as the id.
- `tests/test_tags.py`: 26 tests (name resolution, selection, ids/skipids handling, the dispatch in `main`, and `update` against a fake product list, including a control that a normal update does remove a game that left the account while a tag-limited one does not).

DIFFERENCE: `update` writes the new field `tag_names` to the manifest and may save the manifest even when it has nothing else to change (when only a tag changed). Everything else is new options; without them nothing changes.

## 0.5.38 - 04.11.2026 - Optional BLAKE3 checksums kept in the manifest

- GOG publishes only MD5, so BLAKE3 cannot be checked against anything from GOG. It is a **local fingerprint**: the first time a file passes `verify`, its BLAKE3 is stored in the manifest entry (field `blake3`) - "trust on first verify". A later full verification (`verify -forceverify`) then compares only that BLAKE3 instead of computing the MD5 again, which detects any change since the file last passed (bit rot), and is faster on fast disks (BLAKE3 can use several threads and a memory-mapped file).
- Optional: needs the `blake3` package (`python -m pip install blake3`). Without it the program behaves exactly as before and says so once per `verify` run. New option `-noblake3` (also a config setting under `[verify]`) switches the feature off.
- A baseline is recorded only for content that was actually confirmed: a file whose MD5 matched, or - for types GOG gives no MD5 for (`.zip`, `.001`, ...) - a file with a known size that passed the size check (the zip test follows). Nothing is recorded when `-skipmd5` was used for a file that has an MD5, and nothing is recorded or compared for an MD5-less file that is flagged as changed (its recorded value may describe the old content).
- If the BLAKE3 differs and the MD5 is known, the MD5 decides: a mismatch is reported as before (`wrong checksum (md5)`); a match means the stored BLAKE3 was stale, so it is refreshed with a warning. Without a usable MD5 (`-skipmd5`, or a type without MD5) the failure is reported as `changed since last verification (blake3)`. A file that fails is cleaned/deleted as usual and loses `prev_verified`.
- A matching BLAKE3 clears the change mark exactly like an MD5 match (only an MD5-verified file can have one).
- `update`: the BLAKE3 is carried over to the new entry when MD5, size and language are unchanged (also across a rename), and dropped when the MD5 changed. For an MD5-less file it is carried like `prev_verified`, and `-strict` drops it too. New entries get `blake3=None`; manifests from older versions simply lack the field.
- New helper `hash_file()` computes MD5 and/or BLAKE3 in one read pass; `hashfile()` and `hashstream()` are unchanged.
- The summary of `verify` gets three lines when BLAKE3 is active: matches, recorded, mismatches.
- Files that were verified before this version have no baseline: run `verify -forceverify` once to record them (a normal `verify` skips files that are marked as verified). Files downloaded later are verified, and so recorded, by the next `verify`.
- `tests/test_blake3.py`: the tests use a stand-in module with the same small interface, so they run without the package. The real package was **not** available where this entry was written, so it was not run against the real library; the code uses only `blake3.blake3(max_threads=blake3.blake3.AUTO)`, `update()`, `update_mmap(path)` and `hexdigest()`, each guarded with a fallback.

DIFFERENCE: with the package installed, `verify` records BLAKE3 values in the manifest and `-forceverify` compares them instead of the MD5 for files that have one. Without the package, or with `-noblake3`, nothing changes.

## 0.5.37 - 03.11.2026 - JSON token storage and legacy changelog compatibility

- Fix `handle_game_updates()` for older manifests that do not contain a `changelog` field.
- Store tokens in `gog-token.json`. The default is password-based AES-256-GCM encryption with a scrypt-derived key; the password is requested at most once per process and is never stored. `GOGREPO_TOKEN_MODE=plain` explicitly opts into unencrypted JSON for unattended use.
- Read `gog-token.dat` only when the JSON file is absent, migrate its contents to the JSON file, and leave the legacy file unchanged. A corrupt or undecryptable JSON file never triggers a legacy fallback.
- Add regression tests for the missing changelog and token migration/encryption behaviours.
- Add a comment recording the future plugin-system idea; no plugin loader is implemented.

## 0.5.36 - 02.11.2026 - The tests no longer write into the folder they are started from

- Found while packaging this version: after a test run the working folder held a `gog-manifest.dat` and a `gog-manifest.dat.bak` that nobody had asked for. The
  hook tests of `-ids` / `-skipids` in `tests/test_ids.py` (introduced with entry 24) run `verify`, `import` and `backup` on a made-up library of twelve games. They replaced
  the manifest *loader* but not the manifest *saver*, and these commands save the manifest at the end, into the current folder.
- That is a hazard: if the suite is started from a folder that also holds a real library, its `gog-manifest.dat` is overwritten with the made-up one, and after a second run the
  `.bak` is too. A canary file in the starting folder showed exactly that before the fix. No test of the program itself was wrong; the tests were.
- Fixed at the root: `tests/_bootstrap.py` now runs the whole test process in a scratch folder (it changes into it before the script is imported, because the script opens
  `gogrepo.log` in the current folder when it is loaded) and removes it at the end. The hook tests also patch `save_manifest` now, so the cause is not only hidden.
  `tests/test_isolation.py` guards it: the tests run in the scratch folder, a manifest saved with the default path lands there, the script's log file is there, and the scratch folder is outside the
  repository and the starting folder.
- Checked with a canary: the full suite started from a folder holding a `gog-manifest.dat` and a `.bak` passes, leaves both byte for byte as they were, creates nothing there, and no scratch folder is left over.
- If you ran an earlier version of the suite from a folder that holds a real library: look at its `gog-manifest.dat`. A manifest of exactly twelve games (`beneath_a_steel_sky`, `dune`, `gakkou`, ...)
  is the made-up one. `update -full` builds the manifest again from your GOG account (the downloaded files on disk are not touched by that).

DIFFERENCE: none for the program; only the tests changed.

## 0.5.35 - 01.11.2026 - `update` warns when it is about to narrow the manifest

- Found in a real log (30 October): an `update` with a typed `-lang` (and another with a typed `-os`) replaced the installers of the games it fetched by the ones for that
  language and system only, as an update always does. Extras are not filtered, so they stayed. The next full update added the installers back as new entries, and
  `download` marked 216 of them "for change" and had to check them again. Nothing was lost and almost nothing was downloaded, but it cost a long check, and in
  between a `clean` would have moved all those files to `!orphaned`.
- Before a new update starts (not while it resumes an interrupted one; after that, the update that was asked for is checked), `warn_if_update_narrows_manifest()` compares
  the manifest with the operating systems and languages the update will use. It counts the installer entries (`downloads`, `galaxyDownloads`, `sharedDownloads`) that
  the update would drop for the games it could fetch (all games, the ones named with `-ids`, without `-skipids`), using the same filter as the update itself
  (`filter_languages`, with the English fallback of the default language, so that fallback is not reported). It then warns in three lines: what the update is limited to,
  how many installer files of how many games would go and why (which systems, which languages); what that means (the files stay on disk, `clean` would move them to
  `!orphaned`, a later update adds the entries back as new ones, `download` checks them again); and what to do (stop with Ctrl-C and run update again with all systems and
  languages, or put them in the config file).
- It only warns, as decided. It says "up to N" for an update without `-full`, because only the new and updated games are fetched then and that is not known beforehand;
  with `-full` it says "every game". Extras are not counted. The `-installers` option is not taken into account.
- tests/test_update_warning.py: the counting (systems, languages, strict language, the English fallback, both together, `-ids` also as the name on GOG, `-skipids`, ids that are
  not in the manifest, old manifests without the galaxy and shared lists, extras, empty input), the wording, and that `cmd_update` checks once with the lists it will use,
  also for the update that follows a resumed one.

## 0.5.34 - 01.11.2026 - The log starts every run with the version of the program

- Asked for after the analysis of a real log, which did not say which version of the program had written it. The first line of every run in the
  log file `gogrepo.log` is now, for example: `2026-11-01 09:00:00 | INFO     | gogrepo_delta.py version 0.5.34 (Python 3.14.0, Windows-11-10.0.26100-SP0)`.
  It names the version, the Python and the operating system.
- It is written to the log file only, not to the console, so it adds nothing to what is printed, and a `list` that is piped stays clean. It comes
  before everything else a run logs (the notes about the config file, for instance). With `-nolog` nothing is written, as before; `--help` and
  `--version` do not start a run and write nothing.
- `version_line()` builds the text; `process_argv()` writes it as soon as the log file is attached.
- tests/test_log_header.py: the line is first, names version, Python and system, is in the layout of the other lines, comes once per run, and
  stays out of the console, out of `list` output and out of runs with `-nolog`.

## 0.5.33 - 01.11.2026 - `list` says why a search finds nothing when the filter removed the games


- Found in a real log (30 October): a `list ultima` with a language that the Ultima games do not have said "no game matches 'ultima'", although the games are in the manifest (`-ids` found them at once). The words had matched; it was the language filter that took the games out of the list.
- Now, if the words fit games that the operating-system / language filter removed, the message says so: "3 games match 'ultima' (title, title, title) but none has files for the chosen operating system / language." Up to five titles are named. It also names the filter in use (`-os`, `-skipos`, `-lang`, `-skiplang`) and says that it may come from the config file, which is easy to forget.
- If the words fit no game at all, the message is as before ("no game matches ...", with suggestions). The suggestions now come from all games in the manifest, not only from those that passed the filter.
- A filter that leaves nothing when no words were given ("no game has files for this operating system / language") now names the filter in use too.
- In every case the run ends with exit status 1 and a failure in the summary, as before.
- tests/test_ids.py, ListCommandTests: words matching filtered-out games, the filter being named (typed and skip variants), the count and the "and N more" for many games, suggestions with a filter set, the empty-filter message, and games that pass the filter being listed as before.

DIFFERENCE: only the wording of the messages and the source of the suggestions (all games).

## 0.5.32 - 01.11.2026 - The download summary counts what was really downloaded

- Found in a real log (30 October): after an update with a narrowed language, the next full update re-added 216 installers as new, and
  download marked them "for change". Chunk by chunk they were all already right on the disk, so only one file (100 MB) was fetched,
  and the 208 GB were checked locally in four minutes. The summary nevertheless said "files downloaded: 216 (208.41GB)".
- Now the bytes that really arrive are counted per file (job.transferred, filled by _download_ioloop, the only place that receives
  data). In the summary: "files downloaded" counts the files of which data was fetched and shows the amount that came from GOG (for a
  fresh download that is the size of the files, as before; for a file repaired chunk by chunk it is only the chunks that were fetched),
  and the new line "files verified in place (nothing downloaded)" counts the files that were marked for change but needed no data,
  with their size. "files recovered from an earlier run" is unchanged.
- tests/test_run_summary.py: TransferSummaryTests (the figures are checked against the bytes the fake server really sent; the rig server
  now counts them: file_bytes) and FinishProvisionalClassificationTests.

DIFFERENCE: the size shown after "files downloaded" is now the data transferred, which is smaller than before when files were only
  repaired or checked. Scripts that read the summary line "files downloaded" still find it; the checked files are a new line.

## 0.5.31 - 01.11.2026 - Bug fix: atomic_write_text could close a file descriptor that no longer belonged to it

- Found in the review of entry 30. After os.fdopen() took over the descriptor of the temporary file, the with block closed it; if a
  later step failed (typically the final rename, when a virus scanner holds the file on Windows), the error handler called
  os.close() on the same number again. By then another thread may have opened a file and received that number, and it was closed
  under that thread's feet ("Bad file descriptor"), for example a download in progress. The descriptor is now closed by the error
  handler only when no file object took it over (fd is set to None once it has). Rare (a failed save is needed), but the damage
  would have landed on an unrelated file.
- tests/test_atomic_save.py, DescriptorOwnership: a failed swap and a failed write close nothing twice and keep the old file,
  another thread's file survives a failed save, and a descriptor that no file object owns is still closed exactly once.

## 0.5.30 - 31.10.2026 - Security hardening and compatibility-preserving data loading

- Replaced eval-based loading of legacy manifests, resume manifests, config and tokens with
  ast.literal_eval plus recursive AttrDict conversion. Legacy text remains readable.
- Atomic writes now use uniquely-created temporary files; token files are explicitly private
  (0600 on POSIX), including on first creation. Existing file permissions remain preserved.
- Download retry delays no longer hold the shared job lock; response/watchdog cleanup is
  performed in finally blocks.

## 0.5.29 - 31.10.2026 - Credits; test_download_loop.py replaced by the repository owner's version

- __author__ now lists the authors of this version too: eddie3, kalanyr (the original projects), MarS301 and claude.ai.
- tests/test_download_loop.py is the version written by the repository owner and is used as it is from now on. The only change
  against the earlier file is test_restarting_does_not_create_threads: it no longer counts all the threads of the process
  (other threads starting or ending at that moment could disturb the count, which showed on Windows) but checks that the stall
  watchdog still has the same timer thread, and that it is alive, after 20000 pause()/resume() calls. It still fails when a
  timer thread is started for every chunk again.

## 0.5.28 - 31.10.2026 - Bug fix: download left finished files in !provisional when nothing else needed downloading

- Known since the refactoring. An interrupted run can leave completely downloaded files in !downloading/!provisional (they are moved to
  their folders at the end of a run). The next run found them, but if no other file needed downloading it stopped at "nothing to
  download" before moving them, so they stayed there until some later run happened to download something else. Now it says
  "nothing else needs downloading; moving N completed file(s) ... to their place", moves them (which also resets the
  "needs update" flags and saves the manifest, as in a normal run), removes the empty folders, and the summary at the end counts
  them under "files recovered from an earlier run". With nothing left in !provisional the run still says "nothing to download".
- tests/test_download.py: the rig scenario provisional_only (everything in place except one finished file in !provisional) now has
  tests for the file being moved, for the message, and for the summary count.

## 0.5.27 - 31.10.2026 - Config file: a remark about commas and lower case; the project address is the new repository

- The header of the generated file now says that lists are separated with commas (not with spaces or semicolons), and that the
  section names and the values of os and lang are written in lower case while option names may be in any case. That is how the
  program behaves (checked, and kept true by tests): "os = windows linux" and "os = windows; linux" are refused, "os = Windows" and
  "lang = DE" are refused, "[COMMON]" is ignored with a warning, "OS = linux" and "DryRun = true" work, and ids of games may be
  in any case (names are compared ignoring case). Only new files get the remark; a file made earlier is never changed.
- __url__ (shown in --help) and REPO_HOME_URL (used by update_self, which is not connected to any command) now point to
  https://github.com/MarS301/gogrepo_delta. __author__ and the history above keep the credit to the original projects.

## 0.5.26 - 31.10.2026 - Bug fix: the chunk-verification retry loop did not wait before trying again

- Known since the refactoring. When a chunk of a file that is verified against GOG's MD5 data arrives incomplete,
  _download_with_chunk_verification logged "will retry in Ns..." and then tried again at once, so all the retries were used up within
  moments, on a connection that had just failed. The plain download loop has always waited. It now waits HTTP_RETRY_DELAY
  (config setting http_retry_delay) before each retry, and not after the last try. It waits outside job.lock, so the other
  downloads are not held up (the plain loop does hold the lock while it waits; see the known issues).
- tests/test_chunk_retry.py: a chunk that arrives at once needs no wait; one that fails once is retried after the delay; the number
  of retries and the waits between them follow the settings; no wait after the last try, after an HTTP error or after an unexpected
  Content-Range; the lock is free while waiting; the plain loop waits the same time.

DIFFERENCE: a download with chunk verification that hits incomplete chunks now takes up to http_retry_count x http_retry_delay
  seconds longer before it gives up (4 x 5 s with the default settings); that is what the message always promised.

## 0.5.25 - 31.10.2026 - Bug fix: fetch_chunk_tree raised NameError for an old manifest and a signed download address

- Known since the refactoring (it was listed under the known issues). When a game has no api_downlink in the manifest (a manifest
  made before it was stored) and its download address carries the signed parts (wsSecret, wsTime, prefix), the warning used the
  name `d`, which does not exist in that function. NameError is not caught there or in the download worker (only IOError is), so
  the downloader thread ended with an exception and its file was left unfinished. The warning now names the file as the other
  warnings of the function do, and the function returns None, so the file is downloaded without chunk verification, as was
  intended. (The same wording in fetch_file_info is fine: `d` is its parameter.)
- fetch_chunk_tree had no tests. tests/test_chunk_tree.py now covers every branch: file types without checksums, the api_downlink
  way, the old way with and without a signature, and every error that is caught (404, other HTTP errors, bad XML, connection
  and decoding errors).

## 0.5.24 - New command: list (search the manifest by name), and friendlier -ids / -skipids ("did you mean ...")

- list [words] [-os ...] [-lang ...] [-format table|ids]: the games in the manifest, or those whose id, title or name contain all
  the words (any order, any case, accents and punctuation ignored, parts of words match; an id is found by 4 or more digits).
  Table columns: ID, TITLE (what -ids takes), NAME (as on GOG), OS, LANG, FILES, SIZE. -format ids prints only the titles, one per line.
  Reads the manifest only (no login, no network). No match: suggestions and exit status 1. The words go before the options
  (an option like -os takes everything after it as values). The table is on stdout, the messages are on stderr, so it can be piped.
- -ids and -skipids in download, verify, import and backup now go through resolve_game_ids():
    * an exact title or id selects a game, as always (exact wins);
    * otherwise a name that differs only in case, accents, punctuation, underscores or spacing selects it, if it fits ONE game
      ('Beneath a Steel Sky (1994)', 'Ultima IV: Quest of the Avatar', "Baldur's Gate"); the log says what it was taken as;
    * a name that fits several games selects none of them and names them; a game is never selected because it looks a bit like
      the text (suggest_games only suggests: typos, parts of a name, other word order; at most 3, none for texts under 3 letters);
    * words of one name typed without quotes (-ids Beneath a Steel Sky) are recognised and the message shows the quoted form.
  Whatever matches no game is logged with the suggestions and recorded as a failure, so the run ends with exit status 1;
  the games that did match are still processed. -skipids is resolved the same way (a typo there used to skip nothing, silently);
  in download both are looked up among all games, so a skip id outside the games selected by -ids is not a failure.
- update is NOT changed: it checks -ids against the GOG account while scanning, not against the manifest.
- Names: normalize_name() keeps letters of every script as they are and only drops accents on Latin letters, so Japanese names that
  differ by a voiced mark stay different; trade mark signs and apostrophes are dropped, other punctuation becomes a space.

DIFFERENCES: (1) -ids / -skipids names are matched more widely (long titles etc.). (2) A -ids / -skipids entry that matches no game
  now makes the run fail (exit status 1) and is reported, also when other ids matched, and in import and backup where it was silent;
  a scheduled run with a stale id in -skipids now ends with 1. (3) The notice about a newly created config file goes to stderr.

Fixed on the way: with a config file present, a positional argument that takes several values (the list words) was cut to one.

Checked: tests with titles in the style of a real manifest (long titles, trade marks, apostrophes, accents, Japanese, look-alike
  names), mutation checks, the offline download rig (old and new agree in all 69 scenarios apart from the new message in
  ids_not_found and the known nondeterministic order of file names in one warning: 2 of 10 runs differ for the old version
  compared with itself, and for the new one), and runs on a real 76-game manifest. Not checked: the real GOG service.

## Entry 23 - Config file: options with the same name in several commands are set once, in [common]

- Requested: whoever sets a new default normally wants it for every command that has the option (os for download and update, ...),
  and can still override it on the command line. [common] now holds any option; an entry there counts for every command that has
  the option, and commands that do not have it ignore it without a warning. A [command] section overrides [common] for that command.
- The generated file lists an option once, in [common], when two or more commands have it, it is of the same kind (a yes/no switch,
  a list, or a single value with the same type, values and default) and it means the same thing in each (the same note in
  CONFIG_NOTES): shared_options(). Options that differ stay in the sections of their commands: installers (a choice in update, a
  yes/no switch in trash), src_dir and dest_dir (different folders in import and backup). savedir (download and export) is shared.
  A command that has nothing of its own gets no section ([clear_partial_downloads]); the section is still accepted if written by hand.
- A value in [common] that does not fit one command (installers = both for trash) is an error naming that command, only when that
  command is run. An entry in a command section for an option that excludes another (skipos) replaces the [common] entry of the
  excluded option (os) for that command; two excluding entries in the same section are an error.
- The generated file went from 229 to about 190 lines. Files made by earlier versions still work (same keys; [common] is wider).

## Entry 22 - The generated config file is shorter and clearer (469 lines became about 230; nothing about reading the file changed)

- Found when the generated file was looked at on a real machine: a blank line and a 2-3 line comment for every one of 123 entries,
  the same options explained again in up to five sections, and the description of a section sitting right above the comment of
  its first option, so that it read as part of that option's text.
- Now: a header of a few lines; [settings] in six commented groups (SETTING_GROUPS) instead of one paragraph per setting (the
  built-in default is the value that is written, so "(default: x)" is gone; delete the file to see the defaults again); one short
  line per option, written by hand in CONFIG_NOTES; options that belong together (os/skipos, ids/skipids, the skip... family, ...)
  are listed together under one comment that names each of them ("os: ...; skipos: ..."); an option is explained where it first
  appears and listed without a comment in later sections, except where it means something else in another command (installers
  in update and trash, savedir in download and export, src_dir/dest_dir in import and backup), which get their own note;
  options with a fixed set of values show it ([noresume|resume|onlyresume]); no blank lines between entries.
- An option without a note (a flag added later) still appears, with the first sentence of its help text. The tests insist
  that every option has a note, that no note names an option that does not exist, and that every setting is in exactly one group,
  so adding a flag means adding a line to CONFIG_NOTES. SETTINGS now has four fields (the explanation moved to SETTING_GROUPS).
- An existing config file is never replaced, so a file made by the previous version keeps working as it is (checked: same keys,
  same sections); delete it to get the new layout.

Checked with a real manifest (76 games, 217 files): export gives the same CSV with the old file, the new file and no file.

## Entry 21 - Windows: "is anybody there to answer?" (found when the tests were run on Windows 11 / Python 3.14)

- _stdin_is_interactive() relied on sys.stdin.isatty(). On Windows that is also true for the NUL device (what a scheduled task
  or "command \< NUL" gives as input), so a scheduled run printed the question "Use the backup copy ...? [y/N]", read nothing
  and carried on as if the answer was no, instead of saying that the run is not interactive. The outcome was the same (the
  run stops with exit status 1 and the manual instructions), but with a dangling question and without the explanation.
  On Windows it now also asks the console API (GetConsoleMode, via ctypes) whether standard input is a real console.
- The tests that start the script as a subprocess now give it no input (stdin=DEVNULL); before, they inherited the input of
  the test runner, which on a real terminal made the script wait for an answer (a 120 s timeout in one test).

Checked here: the decision logic and the way the console API is called (with a stand-in for it). Only a real Windows run can
  show that GetConsoleMode really answers "no" for NUL; the test test_a_missing_manifest_with_a_backup_stops_a_scheduled_run
  starts the real script with no input and checks for the message, so running the test suite on Windows covers it.

## Entry 20 - Renamed to gogrepo_delta, version 0.5.19, and a config file (gogrepo_delta.cfg)

- Script file and program name are now gogrepo_delta.py (__appname__, the --version text, the User-Agent GOGRepoDelta/0.5.19).
  Nothing else was renamed: gogrepo.log, gog-manifest.dat, gog-token.dat, gog-resume-manifest.dat, gog-config.dat and the
  logger name keep their names, so an existing library and log keep working.
- Config file: INI format, gogrepo_delta.cfg in the folder the program is started from (like the manifest). Set the
  environment variable GOGREPO_DELTA_CONFIG to use another file. When the program is started and there is no such file,
  it is created with every setting and every command-line flag at its default, each with an explanation (ensure_config_file;
  only when the script is run, not when it is imported). An existing file is never changed by the program.
- [settings] holds the former hard-coded values: log_max_mb, log_backups, http_retry_count, http_retry_delay, http_timeout,
  http_no_retry_codes, download_chunk_size, download_threads, progress_interval (was a fixed 1 s sleep), resume_save_threshold,
  summary_max_items, max_listed_failures, file_replace_attempts, file_replace_delay. The built-in defaults are the old values,
  so without a file (or with the generated one) nothing behaves differently. They are read when the program starts, because
  the constants and some default arguments are built from them. A wrong value stops the program with a message that names
  the file, section, key and the reason; an unknown key is a warning. An empty value means "use the default".
  NOT moved: HTTP_FETCH_DELAY (defined but used nowhere), the GOG addresses / client id / secret, file names, the language
  and operating-system tables (not settings; decided with the requester).
- Flag defaults: section [common] (nolog, debug, manifestformat) and one section per command, with one key per flag, named
  like the flag without the dash. Precedence: typed on the command line, then [command], then [common], then the built-in
  default. Built from the real parser (build_parser), so the file and the flags cannot drift apart.
    * yes/no flags: true/yes/on/1 means "as if the flag was typed" (also for the flags that turn something off);
      false or empty means nothing. A flag set in the file cannot be switched off from the command line (no -no-xxx); set it to false.
    * lists (os, lang, ids, skipfiles ...): separated by commas, or one per line; spaces inside an entry are kept.
    * a flag typed on the command line replaces the file's entry completely (lists are not merged) and also switches off the
      entries of the flags that exclude each other with it (file "os" is ignored when -skipos is typed). Two entries in the
      file that exclude each other are an error. Abbreviated flags (-skipo) count as typed.
    * folder arguments (savedir, gamedir, src_dir, dest_dir, cleandir) can be given in the file, then they may be left out.
      Typed folders fill a command's folders from left to right, so give all folders of a command in the file or none.
    * login user name and password are never read from the file.
    * an entry for os / lang / ids counts as typed: for lang this means the English fallback of the default language does not apply.
    * help and version never read the file, so a broken file cannot block them.
  The notes at the start of a run list what the file changed (info line "defaults from the config file ..."), only entries
  that differ from the built-in default.
- process_argv was split into build_parser() (all flags) and process_argv() (reads the config, applies it, parses). To
  know which flags were really typed, the command line is parsed a second time with a parser without defaults and with
  optional folder arguments (_explicit_dests); this only happens when a config file with sections exists.

DIFFERENCE: a file gogrepo_delta.cfg now appears in the working folder on the first run. Nothing else changes with the default content.

Not checked: the real downloads and the real GOG service (as before). Windows and macOS were not tried; the config code uses
  only standard Python and plain relative paths, and the tests do not depend on the operating system. The file is read as
  UTF-8 (a byte order mark is accepted) and written as UTF-8 with the line endings of the system.

## Entry 19 - Login: new captcha detection and a switch to force browser login (requested after GOG changed its login page)

- login_form_has_captcha(): the automatic login looks for a captcha in GOG's login form before it sends the password. It
  now recognises both the old Google reCAPTCHA box (div "g-recaptcha form__recaptcha") and the new captcha field list
  (ol "form__fieldset form__fieldset--captcha", taken from a capture of the changed page). Matching is on the exact class
  text, as before. Before, the new page was not recognised, so the password was sent to a page that could not complete
  the login and the run ended with "Galaxy login failed".
- New switch: login -browser (also --browser). No user name or password is asked for or sent, and GOG's login page is not
  read at all, so a captcha or any other change to that page cannot break it. The sign-in page's address is shown and the
  default browser is opened on it; the person signs in there and pastes the address the browser ends up on
  (.../on_login_success?...&code=...). The code in it is swapped for the token as before. Meant as the way out when the login
  page changes again. A user name / password given together with -browser are ignored with a warning.
- The automatic login, when it meets a captcha (or cannot find the login form), still shows the address and asks for the pasted
  address as before; it now also points to -browser. It does not open a browser by itself.
- The paste step is shared (ask_for_signed_in_url, login_code_from_url) and no longer breaks on spaces or a line break around
  the pasted address; the pasted address (it holds a one-time code) is never written to the log.
- The login command is split into small functions (galaxy_auth_args / galaxy_auth_url, browser_login, _login_with_password,
  _save_login_token). The password flow itself is the old code, moved unchanged apart from the three points below.
- Fixed on the way: an \<input> without an id on the login page raised KeyError (now ignored); a login code that GOG refuses
  (used twice, too old, network problem) gave a traceback and is now a message that says what to do.

DIFFERENCE: the login command now exits with status 1 when the login failed (it always exited with 0 before, also after
  "Galaxy login failed"), so scripts can tell. Nothing else in the normal login changed.

Not checked: the real GOG login pages and token service were not reachable from where this was written. The detection was
  tested on small stand-in pages that contain the elements named above, not on a saved copy of GOG's page; the browser flow
  was tested with GOG's answers faked. Whether GOG shows Google / Discord sign-in on this page, and so whether -browser works
  for such accounts, is not known.

## Entry 18 - End-of-run summary and exit status (requested)

- Every command reports what it did, and main() logs it before the total time ("-- summary: \<command>"): files downloaded
  (with size), already up to date, skipped, recovered from an earlier run; games added / re-checked by update; files
  verified, copied, imported, moved to the orphan folder, deleted. Failures are listed one per line with the reason.
- Failures: a file that could not be downloaded (HTTP error, incomplete, thread crash, or never attempted) or exists twice;
  a game update could not fetch; a file verify found missing / with the wrong size / wrong checksum / failing the zip
  test; a backup source file with the wrong size; a file or folder clean / trash / clear_partial_downloads could not move
  or delete.
- Exit status: 0, or 1 if there were failures. Fatal errors still exit with 1, Ctrl-C prints the summary of what was done
  so far and exits with 1. Note that verify now exits with 1 whenever it finds a problem, including files that are missing.

DIFFERENCE: the exit status can now be 1 for a run that completed; an update that fails for one game still goes on with
  the others (and still drops that game from the resume list, as before) but now reports it.

## Entry 17 - A missing or damaged manifest: use the backup, never an empty list (requested)

- Before, a manifest that was not found was treated as an empty library, so the next update would rebuild everything and
  overwrite the backup history; a manifest that could not be read gave a traceback.
- Now, if gog-manifest.dat is not found (or is damaged, not valid UTF-8, or cannot be parsed) and gog-manifest.dat.bak
  exists, the program says what is wrong, shows the backup (date and size; it is the manifest as it was before the last
  save) and asks "Use the backup copy ... instead? [y/N]" (y, yes, j, ja). Yes: the backup is checked, restored as
  gog-manifest.dat (a damaged file is kept as gog-manifest.dat.damaged, never thrown away) and used.
- If the answer is no (or there is no backup) and the command is 'update', a second question follows: "Start a new, empty
  manifest ... instead? [y/N]". Yes: the damaged file and the old backup are kept (.damaged, .oldbackup, because later saves
  would overwrite the backup) and update starts from scratch. No: it stops with exit status 1, and only now explains how to
  copy, move or delete by hand. Other commands (clean, trash, download, ...) never offer a new manifest, since an empty one
  is useless for them or dangerous (clean would treat every game folder as an orphan): they stop with that explanation.
- A run without a terminal (scheduled task) asks nothing and stops with exit status 1 and the same explanation.
- No manifest and no backup is still the normal first run. A manifest that exists but cannot be read (no permission, locked
  by another program) now stops with a message instead of being treated as empty. A missing resume file is normal and
  never asks.

## Entry 16 - Text in any language (checked after a question about Chinese characters)

- Manifest (JSON and old format), log file, !info.txt / serial files and the export were already read and written
  as UTF-8, so Chinese, Japanese, Korean, Russian, Arabic, Thai, accents and emoji work in all of them.
- Fixed: console output that is redirected on Windows (scheduled task, "> file", pipe) uses the legacy code page.
  A log line with characters outside it caused a "Logging error" traceback and was lost, and print() crashed.
  Such characters are now shown as \uXXXX escapes (the log file has the real characters).

## Entry 15 - Faster, still readable manifest, and an export command (requested)

- The manifest and the resume manifest are now saved as indented JSON (one field per line, keys sorted, special
  characters not escaped) instead of Python text. Any text editor can open it. Measured with this script on a
  synthetic library of 1500 games (12 MB): save 3.0 s -> 0.4 s (this includes the read-back check below and the .bak
  copy), load 2.9 s -> 0.09 s. The plain json module alone is faster still, the rest is the safety net.
- Old-format files load as before (a JSON file is recognised by its first character, '{'). -manifestformat legacy
  writes the old format, for example to keep using other gogrepo versions.
- Safety: every JSON save is read back and compared with the data; if something would not come back exactly
  (tuples, non-text dict keys, NaN, ...) that save uses the old format and says so. The first JSON save over an
  old-format file keeps that file as \<file>.legacy (made once, never overwritten); if the copy fails the format is
  not switched. The usual \<file>.bak still holds the previous version and saves stay atomic. A damaged JSON file
  gives a message that points to the .bak instead of a traceback.
- The JSON loader does not have a limitation of the old loader, which misread { and } in game titles (and, in resume
  files, in changelogs).
- New command: export [-output FILE] [-savedir DIR] [-delimiter C] writes a CSV spreadsheet, one row per file
  (game, kind, file, operating system, language, version, size, md5, date); with -savedir an "on disk" column says
  yes / no / wrong size (sizes only, no checksums). UTF-8 with a byte order mark so Excel shows umlauts; the column
  separator is ';' for most languages and ',' for English, Japanese, Chinese, Korean, Thai and Hebrew.

DIFFERENCE: the manifest file has a different layout, and other gogrepo versions cannot read the JSON layout.

## Entry 14 - hashfile() closes the file it opens

Small fix found while testing: hashfile() (used by verify, import and trash) now closes the file it reads.

## Entry 13 - English fallback for the default language (requested)

- Problem: with the default language (say de) a game that has no German version gave you nothing at all.
- Now, when the language comes from the default (no -lang / -skiplang given) and is not English, English is the
  fallback: for every game, per list (standalone / galaxy / shared) and per operating system, the files in
  your language are used if there are any, otherwise the English ones. A game with German and English
  installers still gives only German. Example: German Windows installer + English-only Linux installer
  -> you get the German Windows file and the English Linux file. Languages other than German work the same
  (locale cn: Chinese where available, otherwise English).
- The fallback applies in all five commands (update, download, verify, import, backup) through
  filter_languages(), and in update it is decided on GOG's data (filter_downloads) before any file information
  is requested. It is stored in the resume file (key 'lang_fallback'; old resume files have none = strict).
- An explicit -lang (or -skiplang) is still taken literally: -lang de gives German only, -lang de en gives both.

DIFFERENCE: the default language list now picks up English files for games without your language. A normal
  update only re-fetches new and changed games, so run "update -full" once to give the games already in your
  manifest their English fallback. An update REPLACES what the manifest holds for every game it fetches, so
  English entries that were stored for a game that also has your language are dropped from the manifest
  (the files on disk stay).

Not handled: a language group that contains only a patch (no installer) counts as "has your language" for
  that system, so the English installer would not be chosen for it.

## Entry 12 - Default operating system and language (requested)

- Before: only "update" defaulted to this computer's OS and locale (detected by taking the first two letters of
  locale.getlocale(), which is often empty on Windows, so it quietly fell back to English); download, verify,
  import and backup defaulted to every operating system and every language.
- Now all five use apply_os_lang_defaults(). -os / -lang given: used as they are. Only -skipos / -skiplang
  given: every OS / language except those (as before; -os with -skipos and -lang with -skiplang are rejected by
  the parser, as before). Neither: this computer's OS and the user's language. The choice is logged
  ("no -os given, using ...") so it is visible what a default run does.
- OS: platform.system() (Darwin = mac). Language: locale.getlocale(), then the Windows display language, then
  locale.getdefaultlocale(); locale names are mapped to GOG's codes (ja -> jp, cs -> cz, zh -> cn / zh,
  pt_BR -> br, bg -> bl, ...). If detection fails or finds nothing GOG offers: windows / en.

DIFFERENCE: a plain download, verify, import or backup now handles one OS and one language instead of
  everything. A plain update stores only that OS and language for every game it fetches and REPLACES what the
  manifest held for that game, so entries for other languages / systems disappear from the manifest (the files
  on disk stay, but a later "clean" would treat them as orphans). Use -os / -lang (e.g. -lang en de) to keep them.

## Entry 11 - Lower CPU usage while downloading (reported: 5-10% of an 8-core CPU at only ~6 MB/s)

- The read loop (_download_ioloop) read 4 KB at a time and started a NEW THREAD (threading.Timer, the
  stall watchdog) for every chunk: ~1500 thread creations per second per download at 6 MB/s.
  _StallWatchdog now uses one timer thread per response and DOWNLOAD_CHUNK_SIZE is 64 KB.
  Measured on a local server (CPU of the downloading process only): 22 -> 1.5 CPU-ms per MB over HTTPS
  (21 -> 0.8 over plain HTTP). Most of what is left is TLS decryption.
  Same timeout rule as before: a download is cut off after HTTP_TIMEOUT seconds without data; time spent
  writing a chunk does not count.

DIFFERENCE: a piece of DOWNLOAD_CHUNK_SIZE must arrive within HTTP_TIMEOUT, so the slowest usable
  connection is about 1.1 KB/s (it was about 70 B/s). The timer thread is now a daemon thread, so it can
  no longer delay program exit after Ctrl-C. When a connection drops, the last incomplete piece (up to 64 KB,
  before: 4 KB) of that read is not written to the partial file; partial data is only ever reused in whole
  MD5-verified chunks and files without MD5 data restart from byte 0, so nothing of value is lost.

## Entry 10 - Update speed and interruption (changed after a real log showed the problem)

- cmd_update saved the manifest AND the resume manifest after every game in the default modes
  (-standard, -updateonly, -skipknown); only -full / -ids saved every RESUME_SAVE_THRESHOLD (50)
  games. A save re-formats the whole manifest with pprint (about 9 s on one real library) while
  fetching a game takes about 1 s, so most of a small update was spent saving. All modes now save
  every RESUME_SAVE_THRESHOLD games and once at the end.
  DIFFERENCE: if the process is killed hard (not Ctrl-C), up to 49 fetched games are lost and fetched
  again by the next run. Manifest and resume manifest are always saved as a pair, so resuming is safe.
- Ctrl-C during the fetch loop now saves the games fetched so far and re-raises (press Ctrl-C again to
  skip that save; the atomic save leaves the previous files intact).
- cmd_download now flushes the combined MD5 warnings when it finishes, like cmd_update. Before, they
  were only printed at interpreter exit, after the final "exiting..." line.

## Entry 9 - cmd_download split (it was one function of ~925 lines with nested closures)

cmd_download is now a short orchestrator. Helpers (all module level, shared state in _DownloadJob):
  _select_download_items, _index_items_by_title, _clean_work_dir, _process_download_item,
  _item_download_lists, _write_info_file (+_write_info_entries), _write_serial_file,
  _download_item_images (+_download_image_from_item_key/_keys), _queue_item_downloads,
  _download_worker, _prepare_download_file, _fit_partial_file, _preallocate,
  _download_with_chunk_verification, _download_without_chunk_verification, _download_ioloop,
  _report_progress, _finish_provisional_downloads, _remove_empty_subdirs.

Duplicated code was merged: the two !downloading / !provisional clean-up loops, the two
empty-folder loops, the three !info.txt item loops, and the three copies of the preallocation
logic (Windows CreateFileW and POSIX posix_fallocate; callers still differ only where the old code
did, e.g. the path used for the Windows file system lookup). Dead code removed: the unused
id->item dict, ~30 lines of commented-out code in the worker. The nested closures now take the
session/state as parameters. Log messages, their order per file, and file effects are unchanged.

DIFFERENCE: the Windows preallocation handle is always initialised to -1. Before, if CreateFileW
itself raised while growing a file that had just been moved from its final location, the error
handler failed with UnboundLocalError and that download thread died.

## Entry 8 - Small fixes

- path_preserving_split_ext now uses os.path.splitext: names without an extension no longer raise
  IndexError (moving an orphaned "README" onto an existing "README" used to crash) and a leading
  dot is not an extension (".hidden" -> ".hidden(1)" instead of "(1).hidden").
- numbered_name(): the "(n)" clash naming rule (incl. GOG's multi-part .bin sets) was copy-pasted in
  makeDeDuplicateName and move_with_increment_on_clash; both use it now. makeDeDuplicateName
  no longer raises ValueError for names without an extension.
- is_numeric_id() also catches TypeError (None and other non-strings return False).

DIFFERENCE: the crash cases above now work; dotfile clash names changed as described.

## Entry 7 - Combined MD5 warnings

- note_summarised() / flush_summarised(): repetitive per-file conditions are logged at DEBUG and
  reported once as a combined warning (end of cmd_update and cmd_download, and at exit as a safety net).
- request(..., quiet_statuses=(404,)): a 404 for an MD5 XML file is an expected answer and is no
  longer logged as a warning by request() (it is still raised and handled by the caller).
- md5_xml_url(): URL building split out of append_xml_extension_to_url_path so it is pure.

## Entry 6 - Atomic saves of the manifest, resume manifest, token and config

Atomic saves: atomic_write_text() (+ _replace_file, _fsync_directory) writes to \<file>.tmp,
flushes to disk and swaps it in with os.replace. Used for the manifest (previous version still
copied to .bak), resume manifest, token and config file. Before, a crash between "move to .bak"
and "move into place" could leave no manifest at all; permissions of an existing file are kept.

## Entry 5 - Logging

- Logger renamed 'ws' -> 'gogrepoc'. The log file now has date and level on every line
  (the console format is unchanged).
- Remaining print() calls that were messages now use logging: failed-download marker
  ("! path") is an error() line, Jython notice is error(), update_self() debug dumps are debug().
- Level corrections: verify findings (mismatched size/md5, zip test failed, missing file) and
  "failed - closing outstanding handle" are warnings; the three XML verification messages that
  end in "skipping" went from error to warning.

## Entry 4 - Bug fix: in cmd_import, setattr(entry, "old_updated", updated) used an undefined name

(NameError in a rarely used path); it is now None, like the line before it.

## Entry 3 - Python 2 support removed (Python 3.10+ is required, which the start-up check already enforced)

- Removed: __future__ imports, sys.version_info branches, compat_open (now plain open),
  universalLineEnd / storeExtend (argparse action 'extend'), u'' string prefixes, the Windows
  Python 2.7 long-path workarounds and the Python 2-only imports (dateutil, pytz, string, codecs).
- The "End Of Support for Python 2.7 and 3.8" warning in main() was unreachable (the start-up
  check exits first) and was removed. The start-up errors now go to stderr.

## Entry 2 - Login

- A password given on the command line still works but now logs a deprecation warning (it is
  visible in shell history and process lists). Without it the prompt uses
  getpass.getpass("Password: "), as before.

## Entry 1 - Command line

- GogArgumentParser: every legacy single-dash long option (-skipos, -dryrun, ...) is now also
  accepted GNU style (--skipos, --dryrun). The old spellings work exactly as before.
- add_common_flags(): -nolog / -debug were copy-pasted into all 10 sub-commands, now defined
  once (help typo "doesn't writes" fixed).
- validate_lang_and_os(): the language/os checks were extracted from process_argv, same messages.

## How the early refactoring was checked

How it was checked: the command line parser, atomic saves, combined warnings and the helper
functions have unit tests (tests/). cmd_download was compared with its pre-split version on 66
offline scenarios (local HTTP server with injected faults, fake Windows kernel32, macOS mode):
file tree, manifest, log lines, exceptions, HTTP requests and preallocation calls were identical in
65 (apart from the two combined MD5 notices that item 10 moved to the end of the download); the 66th
(CreateFileW raising) shows the DIFFERENCE above. 98% of cmd_download's statements are
executed by the scenarios; the rest is the unreachable code listed above. tests/download_rig/
contains the rig so any later change can be checked the same way.

Later changes were checked the same way and in addition with mutation checks (breaking the code on purpose to see that the tests notice) and,
where it applies, runs on a real manifest. `tests/README.md` lists what each test file covers.
