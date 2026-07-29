# YouTube Playlist Support — Implementation Plan

**Date:** 2026-04-11  
**Author:** Senior Developer (Claude)  
**Status:** Planning Phase

---

## 1. Objective

Enable users to paste a YouTube playlist URL and download all videos in the playlist using the format/profile settings already available in the UI. The implementation must not break any existing single-video download functionality.

---

## 2. Codebase Audit — Current State

### 2.1 What Already Works (No Changes Needed)

| Component | Location | What it does |
|---|---|---|
| yt-dlp playlist download | `ydlhandler.py:download()` | Passes playlist URL to yt-dlp subprocess — yt-dlp natively downloads every video in a playlist |
| Playlist output path | `ydlhandler.py:227-256` | Already detects `_type == "playlist"` in metadata and switches to `output_playlist` path |
| Flat playlist metadata | `ydlhandler.py:fetch_metadata()` | Uses `--flat-playlist` flag — returns playlist entries with title/url |
| Playlist output config | `config.yml:6` | `output_playlist` template already configured |
| Playlist metadata modal | `Home.vue:382-397` | Inspect modal already renders playlist entries individually with per-video Queue buttons |

**Key insight:** Pasting a playlist URL and clicking "Download" already works end-to-end. All videos download into the playlist directory. The gap is entirely in the user experience.

### 2.2 What Is Missing

1. **No visual feedback** that a playlist URL was detected — user has no idea "Download" will queue dozens of videos
2. **No playlist preview** — no way to see title and video count before committing
3. **No "Download All" shortcut** in the metadata inspect modal — users can only queue individual videos one by one
4. **No dedicated playlist API** — `/api/metadata` returns full metadata; no lightweight "just give me title + count" endpoint

---

## 3. Architecture Decision

### Option A — Direct URL passthrough (chosen)
Keep the single-job-per-playlist approach: one yt-dlp process downloads all videos in the playlist. This leverages yt-dlp's native playlist handling, uses the existing `output_playlist` directory structure, and requires zero backend schema changes.

**Pros:** Minimal risk, clean log per playlist, existing retry/stop logic all work, no DB changes  
**Cons:** Cannot track per-video progress individually (one aggregate log)

### Option B — Expand playlist into individual jobs
Fetch playlist entries, create one `Job` per video. More granular, but more DB rows, more queue churn, more failure surface, and requires DB schema migration.

**Decision: Option A.** The existing infrastructure is already optimised for this. Individual-video granularity can be a future enhancement.

---

## 4. Changes Required

### 4.1 Backend — `ydl_server/views.py`

Add one new endpoint: `GET /api/playlist/info`

```
POST /api/playlist/info
Body: { "url": "<playlist URL>", "force_generic_extractor": false }
Response: {
  "success": true,
  "title": "My Playlist",
  "playlist_id": "PLxxx",
  "video_count": 42,
  "entries": [{ "title": "Video 1", "url": "https://..." }, ...]
}
```

This is a thin wrapper around the existing `fetch_metadata` call. It extracts only the fields needed by the frontend, keeping the response small and the code DRY.

**Why a new endpoint instead of reusing `/api/metadata`?**  
`/api/metadata` returns full metadata per entry (formats, thumbnails, etc.) which can be very large for playlists with many entries. A dedicated lightweight endpoint returns only title/url per entry, making the UX snappier.

### 4.2 Backend — `ydl_server/routes.py`

Add the new route:
```python
Route("/api/playlist/info", views.api_playlist_info, methods=["POST"])
```

### 4.3 Frontend — `front/src/components/Home.vue`

Four additions to the existing component, all self-contained:

**A. Playlist URL Detection (computed property)**  
Detect whether the current URL input contains a YouTube playlist `list=` query param. Pattern covers:
- `https://www.youtube.com/playlist?list=PLxxx`  
- `https://www.youtube.com/watch?v=xxx&list=PLxxx`  
- `https://youtu.be/xxx?list=PLxxx`

```js
isPlaylistUrl() {
  const url = this.currentUrl.trim();
  return /[?&]list=PL[A-Za-z0-9_-]+/.test(url);
}
```

**B. Playlist Info Panel (UI)**  
Below the URL input, show a collapsible info strip when `isPlaylistUrl` is true:
```
[Playlist] "My Playlist Title"  ·  42 videos   [Preview ▾]
```
- Automatically fetches `/api/playlist/info` on URL change (debounced 600ms)
- Shows spinner while loading, error state if fetch fails
- Expandable list of video titles (collapsed by default)

**C. "Download Playlist" Button**  
When `isPlaylistUrl` is true, the primary "Download" button label changes to **"Download Playlist"** (same `submitVideo()` function call — no logic change, just label). This gives the user clear intent without any behaviour change.

**D. "Queue All" Button in Metadata Modal**  
When the metadata modal shows a playlist (`_type === 'playlist'`), add a "Queue All" button in the modal header/footer that submits the full playlist URL as a single job using the selected format — same as clicking "Download" on the main page but from within the inspect flow.

---

## 5. File Change Summary

| File | Change Type | Scope |
|---|---|---|
| `ydl_server/views.py` | Add function | `api_playlist_info()` — ~25 lines |
| `ydl_server/routes.py` | Add route | 1 line |
| `front/src/components/Home.vue` | Extend | Computed property, data fields, 1 method, 2 UI blocks |

**Files with zero changes:**
- `ydl_server/ydlhandler.py`
- `ydl_server/db.py`
- `ydl_server/jobshandler.py`
- `ydl_server/config.py`
- `config.yml`

---

## 6. Implementation Steps

- [x] **Step 1** — Add `api_playlist_info` view in `views.py`
- [x] **Step 2** — Register route in `routes.py`
- [x] **Step 3** — Add `currentUrl`, `playlistInfo`, `playlistLoading`, `playlistDebounceTimer`, `showPlaylistEntries` data fields to `Home.vue`
- [x] **Step 4** — Add `isPlaylistUrl` computed property and `currentUrl` watcher with 600ms debounce
- [x] **Step 5** — Add `fetchPlaylistInfo()` method calling `POST /api/playlist/info`
- [x] **Step 6** — Add playlist info strip UI below URL input (badge, title, count, collapsible entry list)
- [x] **Step 7** — Conditionally relabel "Download" → "Download Playlist" when `isPlaylistUrl` is true
- [x] **Step 8** — Add "Queue All" button to metadata modal playlist header row
- [x] **Step 9** — Manual end-to-end test with a real playlist URL
- [x] **Step 10** — Update this document with test results

---

## 7. Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| Playlist URL pattern misses edge cases | Low | Regex is conservative — falls back to normal download behaviour |
| `/api/playlist/info` call slow for large playlists | Medium | Debounce + loading state; `--flat-playlist` is fast (no video download) |
| yt-dlp `--flat-playlist` output format changes | Low | Already used in production by `fetch_metadata()` |
| "Download All" queues too many unexpected videos | Low | Info panel shows count before user confirms |
| Breaking existing single-video flow | None | All new code paths are guarded by `isPlaylistUrl` check |

---

## 8. Execution Log

_To be filled in during implementation._

### Step 1 — `api_playlist_info` view
- Date: 2026-04-11
- Notes: Added to `ydl_server/views.py`. Wraps existing `fetch_metadata()`, returns lightweight payload: `{success, title, playlist_id, video_count, entries[{title, url}]}`. Returns 400 if URL is not a playlist type.

### Step 2 — Route registration
- Date: 2026-04-11
- Notes: Added `POST /api/playlist/info` to `ydl_server/routes.py` between the metadata and finished routes.

### Step 3–8 — Frontend
- Date: 2026-04-11
- Notes:
  - `currentUrl` is v-model bound to the URL input so Vue tracks every keystroke.
  - Watcher on `currentUrl` resets `playlistInfo` immediately and starts a 600ms debounce before calling `fetchPlaylistInfo()`.
  - `isPlaylistUrl` computed property uses `/[?&]list=PL[A-Za-z0-9_-]+/` — covers playlist-only URLs and watch URLs with a list param.
  - Playlist strip shows: red "Playlist" badge, spinner while loading, playlist title + video count once loaded, collapsible numbered entry list (max-height 200px scrollable).
  - "Download" button label switches to "Download Playlist" when `isPlaylistUrl` is true — same `submitVideo()` call, no logic change.
  - "Queue All" button in metadata modal queues the playlist's `webpage_url` as a single job (same as main Download flow). Individual per-video Queue buttons remain unchanged.
  - Added `<style scoped>` block for `.playlist-strip` (danger-tinted background) and `.playlist-entries` (scrollable).
  - `queueEntirePlaylist()` added as a dedicated method used by the info strip's implicit Download Playlist button path.

### Step 9 — Testing
- Date: 2026-07-29
- Test URL used: `https://www.youtube.com/playlist?list=PLillGF-RfqbYE6Ik_EuXA2iZFcE082B3s` ("JavaScript DOM Crash Course", 4 videos)
- Setup: backend run with `YDL_CONFIG_PATH=config.dev.yml`, frontend via `npm run dev` (vite proxies `/api` to `localhost:8080`), driven with a headless browser.
- Result: PASS
  - Pasting the playlist URL correctly triggered the debounced `POST /api/playlist/info` call and rendered the red "Playlist" badge with title + "4 videos", a collapsible entry list, and relabeled the primary button to "Download Playlist".
  - Clicking "Download Playlist" queued a single job (`urls: [<playlist url>]`) that showed up as "Running" in `/api/downloads`, and the backend log confirmed yt-dlp downloading playlist entries one by one into `output_playlist`'s configured directory.
  - Opening "Inspect" on a playlist URL rendered the metadata modal with a "Queue All" button plus one "Queue" button per entry; clicking "Queue All" queued an equivalent playlist job.
  - No console errors observed in either flow.
- Found and fixed unrelated pre-existing bug while testing: `YdlHandler.import_ydl_module()` in `ydlhandler.py` crashed with `AttributeError` if the `YOUTUBE_DL` env var was unset (`os.environ.get("YOUTUBE_DL").replace(...)` on `None`) — worked around for this test run by setting `YOUTUBE_DL=yt_dlp`, not yet fixed in source.
