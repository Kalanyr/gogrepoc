# Tests for gogrepo_delta.py

Run from the folder that contains `gogrepo_delta.py`:

    python -m unittest discover -s tests                      # everything (~1 minute)
    python -m unittest discover -s tests -p "test_[a-ce-z]*.py"   # fast tests only (< 1 second)

No network or GOG account is needed, and the results do not depend on the operating system: the download rig fakes the platform (Linux, Windows or macOS) and `os.posix_fallocate` itself, so the same tests run on Windows, macOS and Linux. `requests` is required (like the script itself); if `html5lib` or
`psutil` are missing, empty stand-ins are used so the tests can still run.

The tests run inside a scratch folder that is removed afterwards (`_bootstrap.py`), so it is safe to start them from any folder, also one that holds a real library and its `gog-manifest.dat`.

| file | covers |
|---|---|
| test_text, test_paths, test_urls, test_attrdict, test_manifest_logic | pure helpers (slugify, de-duplication, update detection, URL building ...) |
| test_unicode | Chinese, Japanese, Russian, emoji ... in the manifest, export, log file, file names, !info.txt and redirected console output |
| test_hashing | hashfile (MD5 of a file, closes the file) |
| test_moves | move_with_increment_on_clash on real temporary folders |
| test_language_fallback | English fallback for the default language in update (incl. resume), download, verify, import and backup |
| test_defaults | default OS / language detection, fallbacks, and -os / -lang / -skipos / -skiplang for update, download, verify, import, backup |
| test_run_summary | the end-of-run summary and exit status of every command, the entry point, and the real script's exit codes; also that 'files downloaded' counts only data really transferred and checked files have their own line |
| test_manifest_recovery | missing or damaged manifest: the question about the .bak backup, the second question about a new manifest (update only), what is kept, and when the manual instructions appear |
| test_manifest_format | JSON / old manifest formats, migration and its safety copy, fallbacks, resume files, the export command |
| test_cli | command line parser, `--option` aliases, validation |
| test_login | captcha detection (old and new form), the `login -browser` switch, pasted-address handling, the automatic password flow, login exit status (GOG faked, no network) |
| test_config | config file `gogrepo_delta.cfg`: `[settings]` (parsing, limits, reaching the constants), flag defaults (precedence, lists, switches, exclusive flags, folders, `[common]`), the generated file and its compact layout, creating it on the first run; also name and version |
| test_ids | name matching and `-ids` / `-skipids` (exact, normalised, ambiguous, typos, unquoted words), suggestions, `list` command (search, table, filters, output streams), and how download, verify, import and backup use them |
| test_chunk_tree | `fetch_chunk_tree`: every branch of getting a file's checksum data, including the signed-address case that used to raise NameError |
| test_chunk_retry | the retry loop of chunk verification: waits `http_retry_delay` between tries, none after the last, not holding the lock |
| test_log_header | the first line of every run in the log file: version, Python and system (not on the console, not with `-nolog`) |
| test_isolation | the whole test run happens in a scratch folder, so no test can overwrite a manifest or log in the folder it was started from |
| test_update_warning | the warning when an update is about to narrow the manifest: the counting (systems, languages, the English fallback, ids, skipids), the wording, and that `cmd_update` checks once with the lists it will use |
| test_interactive | deciding whether a person can answer a question (terminal, no terminal, Windows console vs the NUL device) |
| test_atomic_save | atomic manifest/token/config saving, crash simulation, private token files, the legacy loader not executing code, and that a failed save never closes a descriptor that is not its own |
| test_summarised_warnings | combined MD5 warnings, quiet 404 handling (real local HTTP server) |
| test_update_saves | cmd_update save frequency and Ctrl-C handling against a fake GOG account API |
| test_download_loop | the download read loop: stall watchdog, 64 KB reads, no thread per chunk |
| test_download | cmd_download end to end against a local fake GOG server |

## download_rig/

`rig.py` is the offline rig behind `test_download.py`. It can also compare two versions of the script,
which is how cmd_download was refactored without changing behaviour:

    python tests/download_rig/rig.py old/gogrepo_delta.py new/gogrepo_delta.py        # all scenarios
    python tests/download_rig/rig.py old/gogrepo_delta.py new/gogrepo_delta.py faults  # selected scenarios
    python tests/download_rig/cover.py gogrepo_delta.py                          # which cmd_download lines the scenarios reach

It runs a local HTTP server (Range requests, MD5 chunk XML, injectable faults) and a fake Windows
`kernel32` / macOS mode for the preallocation code, and compares file tree, manifest, log lines,
exceptions, HTTP requests and preallocation calls.
