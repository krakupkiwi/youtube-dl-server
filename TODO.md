# Improvement TODO

Ordered for implementation: cheap/safe fixes first, then a test safety net,
then refactors that lean on that safety net, then features, then polish.
Check items off as they land; each links back to the file(s) involved.

## Phase 1 — Quick, safe fixes (no dependencies, do first)

- [x] Fix mutable default argument `extra_params={}` in `Job.__init__` (`ydl_server/db.py:57`)
- [x] Remove/fix dead code in `get_ydl_website`: `getattr(info, "home-page", ...)` can never match a real attribute (`ydl_server/ydlhandler.py:31`)
- [x] Harden `api_cut_file` output-path validation to also reject backslashes and null bytes, not just `/` and leading `.` (`ydl_server/views.py:112`)
- [x] Verify the stored PID actually belongs to the expected process before `os.kill` in `api_jobs_stop`, to avoid killing a reused PID (`ydl_server/views.py:219-225`) — implemented via a live Popen registry in `YdlHandler` (`ydlhandler.py`); also fixed a real Windows `SIGINT` bug this surfaced
- [x] Give `api_jobs_stop`/`api_jobs_retry` a `message`/`error` field on failure, matching `api_delete_file`'s pattern (`ydl_server/views.py`)

## Phase 2 — Regression test safety net (before refactoring anything below)

- [x] Set up a `tests/` directory + test runner (pytest) and wire it into CI (`.github/workflows/ci.yml`, `requirements-dev.txt`)
- [x] Tests for DB migration path across schema versions (`tests/test_db_migrations.py`) — caught a real bug: migrating from schema v1 never added the `extra_params` column while still stamping the DB as current; fixed in `db.py`
- [x] Tests for the Windows/Unix SQLite URI logic (`tests/test_sqlite_uri.py`)
- [x] Tests for alias/profile resolution, including recursive alias handling (`tests/test_config_aliases.py`)
- [x] Tests for path-traversal guards: `resolve_finished_file`, `api_delete_file`, `api_cut_file` (`tests/test_path_traversal.py`) — caught two real bugs: `get_static_prefix` didn't split on backslashes (Windows configs silently fell back to resolving downloads to cwd, the same bug class as upstream #152) and `resolve_finished_file` crashed instead of rejecting when given a path on a different Windows drive letter; both fixed in `config.py`

## Phase 3 — Foundational reliability work (do after Phase 2 has coverage)

- [x] Replace `print()` calls with the `logging` module across the backend (levels, timestamps, ship-able output) — added `ydl_server/logging_config.py`, configured before any other import in `youtube-dl-server.py`, debug flag bumps root logger to DEBUG
- [x] Collapse the near-duplicate migration cases in `db.py:121-218` into a single "apply missing migrations" loop — now inspects actual columns present rather than trusting the stored version number
- [x] Add DB indexes on `jobs.status` / `jobs.last_update` (used by `get_jobs_with_logs`, `clean_old_jobs`)
- [x] Fix the log-tailing race in `read_proc_stdout` (`read1()` can lose/interleave output around `proc.wait()`) (`ydl_server/ydlhandler.py`) — log-tailing thread now stops and is joined via a `threading.Event` before the main thread's final read, so the two never call `read1()` concurrently
- [x] Clean up partial download files when a job is aborted, matching what `cut()` already does on failure (`ydl_server/ydlhandler.py`) — parses `[download] Destination:` lines from the captured log and removes the matching `.part` file, never the final output path itself

## Phase 4 — Frontend correctness fixes (small, independent)

- [ ] Fix fragile URL parsing in `DownloadForm.vue`'s `inspectVideo` (`split('\n').join(' ').split(' ')` breaks on blank lines/odd whitespace)
- [ ] Add try/catch + visible error state around the initial mount-time fetch in `Finished.vue` (currently fails silently)
- [ ] Add keyboard support/ARIA roles to clickable `<tr>` rows and sortable `<th>` headers (`Logs.vue`, `Finished.vue`)

## Phase 5 — Frontend features (bigger scope, build on Phase 4)

- [ ] Bulk actions: multi-select retry/delete in Logs and Finished views
- [ ] Replace 5s polling in `Logs.vue` with push updates (SSE or websocket)
- [ ] Paginate `/api/finished` instead of returning the entire tree in one response

## Phase 6 — Community-requested features

- [ ] Cookie support for gated/private videos, config + UI wiring (upstream issue #43)
- [ ] Detect "video not available yet / scheduled" failures and auto-requeue once the scheduled time passes (upstream issue #146)
- [ ] Lightweight "check video quality / verify cookies" endpoint, cheaper than a full metadata fetch (upstream issue #108)
- [ ] Per-extractor conditional yt-dlp options (different output/flags depending on matched site) (upstream issue #68)

## Phase 7 — Ops, security, docs (lowest urgency, do last)

- [ ] Optional API-key middleware toggle for deployments not sitting behind a reverse proxy
- [ ] Document supported Docker platforms / update mechanism in README
- [ ] Add a "recipes" section to README for common format-customization asks (e.g. forcing H264+AAC mp4)
