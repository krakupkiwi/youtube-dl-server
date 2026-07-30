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

- [x] Fix fragile URL parsing in `DownloadForm.vue`'s `inspectVideo` (`split('\n').join(' ').split(' ')` breaks on blank lines/odd whitespace) — replaced with a shared `parseUrls()` helper, also used by `submitVideo` which had the identical bug
- [x] Add try/catch + visible error state around the initial mount-time fetch in `Finished.vue` (currently fails silently) — also fixed the same bug in `Logs.vue`'s `fetchLogs`, which was worse: a failed request silently killed the 5s auto-refresh polling forever
- [x] Add keyboard support/ARIA roles to clickable `<tr>` rows and sortable `<th>` headers (`Logs.vue`, `Finished.vue`) — also fixed the directory-toggle row in `FileTreeItem.vue`; verified via a headless browser that `role`, `tabindex`, `aria-sort`/`aria-expanded` all update correctly and keyboard activation works

## Phase 5 — Frontend features (bigger scope, build on Phase 4)

- [x] Bulk actions: multi-select retry/delete in Logs and Finished views — checkboxes + select-all in `Logs.vue`, checkboxes in `Finished.vue`/`FileTreeItem.vue` (files and directories, threaded through the recursive tree via a `toggle-select` event); both reuse existing single-item endpoints via `Promise.allSettled`, no new backend endpoints needed
- [x] Replace 5s polling in `Logs.vue` with push updates (SSE or websocket) — added `GET /api/downloads/stream` (Starlette `StreamingResponse`); the server itself still polls the DB on a 1s interval but only once regardless of how many tabs are connected, and only pushes a frame when the payload actually changed. Frontend uses `EventSource`, reconnecting on status-filter changes. Verified live in a browser: a queued job appeared within ~2s with zero manual refresh, and repeated filter switches didn't leak connections.
- [x] Paginate `/api/finished` instead of returning the entire tree in one response — implemented as **lazy-loading** instead of literal pagination, since it fits hierarchical data better: `/api/finished` (and a new `?path=` param for a specific subdirectory) now returns only one level at a time, with unopened directories marked `children: null`. `FileTreeItem.vue` fetches a directory's contents on first expand and caches the result. Sorting was moved from a single recursive pre-sort in `Finished.vue` into each `FileTreeItem` sorting its own (possibly lazily-loaded) children, so sort order stays correct at every depth regardless of what's been loaded yet.

## Phase 6 — Community-requested features

- [ ] Cookie support for gated/private videos, config + UI wiring (upstream issue #43)
- [ ] Detect "video not available yet / scheduled" failures and auto-requeue once the scheduled time passes (upstream issue #146)
- [ ] Lightweight "check video quality / verify cookies" endpoint, cheaper than a full metadata fetch (upstream issue #108)
- [ ] Per-extractor conditional yt-dlp options (different output/flags depending on matched site) (upstream issue #68)

## Phase 7 — Ops, security, docs (lowest urgency, do last)

- [ ] Optional API-key middleware toggle for deployments not sitting behind a reverse proxy
- [ ] Document supported Docker platforms / update mechanism in README
- [ ] Add a "recipes" section to README for common format-customization asks (e.g. forcing H264+AAC mp4)
