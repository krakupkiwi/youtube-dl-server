import asyncio
import json
import logging
import os
import re
import shutil
from pathlib import Path

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, StreamingResponse

from ydl_server.config import (
    app_config,
    get_finished_path,
    get_ui_aliases,
    get_ydl_formats,
    is_valid_download_folder_name,
    is_valid_download_folder_path,
    is_valid_download_title,
    resolve_finished_file,
    set_age_limit,
    set_download_folders,
)
from ydl_server.db import Actions, Job, JobsDB, JobType
from ydl_server.jobshandler import JobInsertError, JobInsertTimeout
from ydl_server.ydlhandler import MetadataBusy, MetadataError, MetadataTimeout

logger = logging.getLogger(__name__)

TIMESTAMP_RE = re.compile(r"^(\d+(\.\d+)?|(\d+:)?[0-5]?\d:[0-5]?\d(\.\d+)?)$")


def parse_timestamp(ts):
    seconds = 0.0
    for part in ts.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def prefix_format(prefix, value):
    """Namespace a format segment, tolerating callers that already prefixed it."""
    return value if value.startswith(prefix + "/") else f"{prefix}/{value}"


MAX_TREE_DEPTH = 32


async def parse_download_request(request):
    is_form = request.headers.get("Content-Type", "").partition(";")[0].strip().lower() == "application/x-www-form-urlencoded"
    if is_form:
        data = dict(await request.form())
    else:
        try:
            data = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Invalid JSON request body") from exc
    if not isinstance(data, dict):
        raise TypeError("Request body must be an object")
    for key in ("url", "profile", "audio_format", "format", "folder"):
        if data.get(key) is not None and not isinstance(data[key], str):
            raise TypeError(f"{key} must be a string")
    urls = data.get("urls", [])
    if not isinstance(urls, list) or any(not isinstance(url, str) or not url.strip() for url in urls):
        raise TypeError("urls must be an array of non-empty strings")
    urls = list(urls)
    if data.get("url") is not None:
        if not data["url"].strip():
            raise ValueError("url must be a non-empty string")
        urls.append(data["url"])
    if not urls:
        raise ValueError("'url' and 'urls' query parameters omitted")
    aliases = data.get("aliases", [])
    if isinstance(aliases, str):
        aliases = [alias.strip() for alias in aliases.split(",") if alias.strip()]
    if not isinstance(aliases, list) or any(not isinstance(alias, str) or not alias.strip() for alias in aliases):
        raise TypeError("aliases must be an array of non-empty strings or a comma-separated string")
    force_generic = data.get("force_generic_extractor", False)
    if is_form and force_generic in ("true", "false"):
        force_generic = force_generic == "true"
    if not isinstance(force_generic, bool):
        raise TypeError("force_generic_extractor must be a boolean")
    extra_params = data.get("extra_params", {})
    if not isinstance(extra_params, dict):
        raise TypeError("extra_params must be an object")
    title = extra_params.get("title")
    if title is not None and title != "" and not is_valid_download_title(title):
        raise ValueError("Invalid download title")
    return {**data, "urls": urls, "aliases": aliases, "force_generic_extractor": force_generic, "extra_params": extra_params}


async def insert_job(request, job):
    try:
        await run_in_threadpool(request.app.state.jobshandler.insert_and_wait, job)
    except JobInsertTimeout:
        return JSONResponse({"success": False, "error": "Timed out waiting for the job queue"}, status_code=503)
    except JobInsertError:
        return JSONResponse({"success": False, "error": "Could not add job to the queue"}, status_code=503)
    return None


def build_finished_tree(root_dir, seen=None, depth=0, max_depth=0):
    """List root_dir's contents, recursing at most max_depth levels.

    Directories beyond max_depth get children=None ("not yet loaded" - the
    frontend lazily fetches them via ?path= on expand) rather than eagerly
    walking the entire tree in one response.
    """
    try:
        entries = list(os.scandir(root_dir))
    except OSError as e:
        logger.error("Error scanning %s - %s", root_dir, e)
        return []
    if seen is None:
        seen = set()
    files = []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        stat, is_dir = None, False
        try:
            stat = entry.stat()
            is_dir = entry.is_dir()
        except OSError as e:
            logger.error("Error accessing %s - %s", entry.path, e)
        children = None
        if is_dir:
            key = (stat.st_dev, stat.st_ino) if stat else None
            if (
                depth < max_depth
                and depth < MAX_TREE_DEPTH
                and key not in seen
                and resolve_finished_file(entry.path) is not None
            ):
                seen.add(key)
                children = build_finished_tree(entry.path, seen, depth + 1, max_depth)
        file_info = {
            "name": entry.name,
            "modified": stat.st_mtime if stat else None,
            "created": stat.st_ctime if stat else None,
            "size": stat.st_size if stat and not is_dir else None,
            "directory": is_dir,
            "children": children,
        }
        files.append(file_info)
    return files


async def api_finished(request):
    path = request.query_params.get("path")
    root_dir = Path(get_finished_path())
    if path:
        resolved = resolve_finished_file(path)
        if resolved is None or not os.path.isdir(resolved):
            return JSONResponse({"success": False, "message": "Invalid directory"}, status_code=400)
        root_dir = Path(resolved)
    return JSONResponse(build_finished_tree(root_dir))


async def api_delete_file(request):
    fname = request.path_params["fname"]
    if not fname:
        return JSONResponse({"success": False, "message": "No filename specified"})
    fname = resolve_finished_file(fname)
    if fname is None:
        return JSONResponse({"success": False, "message": "Invalid filename"})
    fname = Path(fname)
    root = Path(os.path.realpath(get_finished_path()))
    if fname == root:
        return JSONResponse({"success": False, "message": "Invalid filename"}, status_code=400)
    if any(part.startswith(".") for part in fname.relative_to(root).parts):
        return JSONResponse({"success": False, "message": "Invalid filename"}, status_code=400)
    metadata_db_path = app_config["ydl_server"].get("metadata_db_path")
    if metadata_db_path:
        metadata_db_path = Path(os.path.realpath(metadata_db_path))
        if fname == metadata_db_path or fname in metadata_db_path.parents:
            return JSONResponse({"success": False, "message": "Invalid filename"}, status_code=400)
    try:
        if fname.is_dir():
            shutil.rmtree(fname)
        else:
            fname.unlink()
    except OSError as e:
        logger.error("Error deleting %s - %s", fname, e)
        return JSONResponse(
            {"success": False, "message": f"Could not delete the specified file (Err {e.errno or 'unknown'})"}
        )

    return JSONResponse({"success": True, "message": "File deleted"})


async def api_cut_file(request):
    fname = request.path_params["fname"]
    data = await request.json()
    start = str(data.get("start") or "0")
    end = data.get("end") or None
    mode = data.get("mode", "fast")
    output = (data.get("output") or "").strip()

    src = resolve_finished_file(fname)
    if src is None:
        return JSONResponse({"success": False, "message": "Invalid filename"})
    if not os.path.isfile(src):
        return JSONResponse({"success": False, "message": "File not found"})

    if not output or "/" in output or "\\" in output or "\x00" in output or output.startswith("."):
        return JSONResponse({"success": False, "message": "Invalid output filename"})
    dst = os.path.join(os.path.dirname(src), output)
    if os.path.exists(dst):
        return JSONResponse({"success": False, "message": "Output file already exists"})

    if not TIMESTAMP_RE.match(start) or (end and not TIMESTAMP_RE.match(str(end))):
        return JSONResponse({"success": False, "message": "Invalid timestamp"})
    if end and parse_timestamp(str(end)) <= parse_timestamp(start):
        return JSONResponse({"success": False, "message": "End time must be after start time"})
    if mode not in ("fast", "precise"):
        return JSONResponse({"success": False, "message": "Invalid mode"})

    job = Job(
        "Cut {} [{} - {}]".format(fname, start, end or "end"),
        Job.PENDING,
        "",
        JobType.FFMPEG_CUT,
        None,
        [fname],
        extra_params={"start": start, "end": end, "mode": mode, "output": output},
    )
    error = await insert_job(request, job)
    if error is not None:
        return error

    return JSONResponse({"success": True, "output": output})


async def api_list_extractors(request):
    return JSONResponse(request.app.state.ydlhandler.ydl_extractors)


async def api_server_info(request):
    return JSONResponse(
        {
            "site_title": app_config["ydl_server"].get("site_title"),
            "ydl_module_name": request.app.state.ydlhandler.ydl_module_name,
            "ydl_module_version": request.app.state.ydlhandler.ydl_version,
            "ydl_module_website": request.app.state.ydlhandler.ydl_website,
            "ydls_version": request.app.state.ydlhandler.ydls_version,
            "ydls_release_date": request.app.state.ydlhandler.ydls_release_date,
            "download_workers_count": request.app.state.ydlhandler.download_workers_count,
        }
    )


async def api_list_formats(request):
    return JSONResponse(
        {
            "ydl_formats": get_ydl_formats(app_config),
            "ydl_aliases": get_ui_aliases(app_config),
            "ydl_default_format": app_config["ydl_server"].get(
                "default_format", "video/best"
            ),
            "ydl_download_folders": [
                f["name"] for f in app_config.get("download_folders", [])
            ],
        }
    )


async def api_get_settings(request):
    return JSONResponse(
        {
            "age_limit": app_config["ydl_options"].get("age-limit"),
            "download_folders": app_config.get("download_folders", []),
        }
    )


async def api_update_settings(request):
    data = await request.json()
    if "age_limit" not in data and "download_folders" not in data:
        return JSONResponse(
            {"success": False, "message": "'age_limit' or 'download_folders' is required"},
            status_code=400,
        )

    age_limit = data.get("age_limit")
    if "age_limit" in data and age_limit is not None:
        try:
            age_limit = int(age_limit)
        except (TypeError, ValueError):
            return JSONResponse(
                {"success": False, "message": "age_limit must be a whole number or null"},
                status_code=400,
            )
        if age_limit < 0:
            return JSONResponse(
                {"success": False, "message": "age_limit must not be negative"},
                status_code=400,
            )

    download_folders = data.get("download_folders")
    if "download_folders" in data:
        if not isinstance(download_folders, list):
            return JSONResponse(
                {"success": False, "message": "download_folders must be a list"}, status_code=400
            )
        normalized = []
        for f in download_folders:
            if isinstance(f, str):
                normalized.append({"name": f.strip(), "path": None})
            elif isinstance(f, dict):
                name = (f.get("name") or "").strip()
                path = (f.get("path") or "").strip() or None
                normalized.append({"name": name, "path": path})
            else:
                return JSONResponse(
                    {
                        "success": False,
                        "message": "Each download folder must be a name, or a {name, path} object",
                    },
                    status_code=400,
                )
        if not all(is_valid_download_folder_name(f["name"]) for f in normalized):
            return JSONResponse(
                {
                    "success": False,
                    "message": "Folder names must not be empty, '.', '..', or contain '/', '\\', or ','",
                },
                status_code=400,
            )
        if not all(
            f["path"] is None or is_valid_download_folder_path(f["path"]) for f in normalized
        ):
            return JSONResponse(
                {
                    "success": False,
                    "message": "Folder paths must be absolute (e.g. /concerts), contain no "
                    "'..' segments, and not be '/'",
                },
                status_code=400,
            )
        names = [f["name"] for f in normalized]
        if len(set(names)) != len(names):
            return JSONResponse(
                {"success": False, "message": "Folder names must be unique"}, status_code=400
            )
        download_folders = normalized

    try:
        if "age_limit" in data:
            set_age_limit(age_limit)
        if "download_folders" in data:
            set_download_folders(download_folders)
    except OSError as e:
        logger.error("Error saving config - %s", e)
        return JSONResponse(
            {"success": False, "message": "Could not save the config file"}, status_code=500
        )

    request.app.state.ydlhandler.refresh_extractors()
    return JSONResponse(
        {
            "success": True,
            "age_limit": app_config["ydl_options"].get("age-limit"),
            "download_folders": app_config.get("download_folders", []),
        }
    )


async def api_browse_dirs(request):
    """List subdirectories of `path` (defaults to the filesystem root) so the
    Settings page can offer a folder picker for download_folders' `path`
    field, instead of the admin having to remember/type container paths by
    hand. In a container this only ever sees what's actually mounted in -
    it's exactly as scoped as the container's own filesystem view, nothing
    on the host beyond that.
    """
    path = request.query_params.get("path") or os.path.abspath(os.sep)
    if not os.path.isabs(path):
        return JSONResponse({"success": False, "message": "Path must be absolute"}, status_code=400)

    normalized = os.path.normpath(path)
    if not os.path.isdir(normalized):
        return JSONResponse(
            {"success": False, "message": f"Not a directory: {normalized}"}, status_code=400
        )

    dirs = []
    try:
        with os.scandir(normalized) as it:
            for entry in it:
                if entry.name.startswith("."):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        dirs.append(entry.name)
                except OSError:
                    continue
    except OSError as e:
        return JSONResponse(
            {"success": False, "message": f"Could not list {normalized}: {e.strerror or e}"},
            status_code=400,
        )

    # os.path.dirname is idempotent at the filesystem/drive root (e.g.
    # dirname("/") == "/", dirname("C:\\") == "C:\\"), which is exactly the
    # "no parent" signal we want.
    parent = os.path.dirname(normalized)
    if parent == normalized:
        parent = None

    return JSONResponse(
        {
            "success": True,
            "path": normalized,
            "parent": parent,
            "dirs": sorted(dirs, key=str.lower),
        }
    )


async def api_queue_size(request):
    db = JobsDB(readonly=True)
    counts = db.get_job_counts()
    db.close()
    return JSONResponse(
        {
            "success": True,
            "stats": {
                "queue": request.app.state.ydlhandler.queue.qsize(),
                **counts,
            },
        }
    )


async def api_logs(request):
    db = JobsDB(readonly=True)
    limit = app_config["ydl_server"].get("max_log_entries", 100)
    status = request.query_params.get("status", None)
    if request.query_params.get("show_logs", "1") in ["1", "true"]:
        result = db.get_jobs_with_logs(limit, status)
    else:
        result = db.get_jobs(limit, status)
    db.close()
    return JSONResponse(result)


async def api_logs_stream(request):
    """Server-sent-events stream of the jobs list, replacing client-side polling.

    The server itself still polls the DB on an interval, but only once here
    regardless of how many browser tabs are connected, and only pushes a new
    frame when the result actually changed - client tabs get near-instant
    updates without each of them hitting the DB on their own timer.
    """
    limit = app_config["ydl_server"].get("max_log_entries", 100)
    status = request.query_params.get("status", None)
    show_logs = request.query_params.get("show_logs", "1") in ["1", "true"]

    async def event_generator():
        last_payload = None
        while True:
            if await request.is_disconnected():
                break
            db = JobsDB(readonly=True)
            try:
                result = db.get_jobs_with_logs(limit, status) if show_logs else db.get_jobs(limit, status)
            finally:
                db.close()
            payload = json.dumps(result)
            if payload != last_payload:
                last_payload = payload
                yield f"data: {payload}\n\n"
            else:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def api_logs_purge(request):
    request.app.state.jobshandler.put((Actions.PURGE_LOGS, None))
    return JSONResponse({"success": True})


async def api_logs_clean(request):
    request.app.state.jobshandler.put((Actions.CLEAN_LOGS, None))
    return JSONResponse({"success": True})


async def api_jobs_stop(request):
    db = JobsDB(readonly=True)
    job_id = request.path_params["job_id"]
    job = db.get_job_by_id(job_id)
    db.close()

    if not job:
        return JSONResponse({"success": False}, status_code=404)
    try:
        aborted = await run_in_threadpool(request.app.state.jobshandler.submit_and_wait, Actions.ABORT, job["id"])
    except (JobInsertError, JobInsertTimeout):
        return JSONResponse({"success": False, "error": "Could not stop job"}, status_code=503)
    if aborted:
        request.app.state.ydlhandler.cancel(job["id"])
    return JSONResponse({"success": aborted})


async def api_jobs_retry(request):
    db = JobsDB(readonly=True)
    job_id = request.path_params["job_id"]
    job = db.get_job_by_id(job_id)
    db.close()
    if not job:
        return JSONResponse({"success": False, "message": "Job not found"}, status_code=404)

    extra_params = job.get("extra_params", {})
    # An explicit retry gets a fresh scheduling budget
    extra_params.pop("schedule_attempts", None)

    new_job = Job(
        job["name"], Job.PENDING, "", int(job["type"]), job["format"], job["urls"], extra_params=extra_params
    )
    new_job.force_generic_extractor = job.get("force_generic_extractor", False)

    error = await insert_job(request, new_job)
    if error is not None:
        return error
    request.app.state.jobshandler.put((Actions.DELETE_LOG_SAFE, job))

    return JSONResponse({"success": True})

async def api_jobs_delete(request):
    job_id = request.path_params["job_id"]
    if job_id is not None:
        request.app.state.jobshandler.put((Actions.DELETE_LOG, {'id': job_id}))
        return JSONResponse({"success": True})
    return JSONResponse({"success": False})

async def api_queue_download(request):
    try:
        data = await parse_download_request(request)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)
    urls = data["urls"]
    profile = data.get("profile")
    aliases = data["aliases"]
    audio_format = data.get("audio_format")
    format_str = data.get("format")
    force_generic_extractor = data["force_generic_extractor"]
    folder = data.get("folder")

    if profile:
        format_str = ','.join(filter(None, [format_str, prefix_format("profile", profile)]))
    if aliases:
        format_str = ','.join(filter(None, [format_str] + [prefix_format("alias", a) for a in aliases]))
    if audio_format:
        format_str = ','.join(filter(None, [format_str, prefix_format("audio", audio_format)]))
    if not format_str:
        format_str = app_config["ydl_server"].get("default_format", "video/best")
    if folder:
        format_str = ','.join([format_str, prefix_format("folder", folder)])
    options = {"format": format_str, "force_generic_extractor": force_generic_extractor}

    extra_params = data["extra_params"]

    job = Job(
        ", ".join(urls), Job.PENDING, "", JobType.YDL_DOWNLOAD, format_str, urls, extra_params=extra_params
    )
    job.force_generic_extractor = force_generic_extractor
    error = await insert_job(request, job)
    if error is not None:
        return error

    logger.info("Added url %s to the download queue", ",".join(urls))
    return JSONResponse({"success": True, "urls": urls, "options": options, "job_id": job.id})


async def api_metadata_fetch(request):
    try:
        data = await parse_download_request(request)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)
    try:
        rc, stdout = await run_in_threadpool(
            request.app.state.ydlhandler.fetch_metadata,
            data["urls"],
            force_generic_extractor=data["force_generic_extractor"],
            wait=False,
        )
    except MetadataBusy:
        return JSONResponse({"success": False, "error": "Metadata extraction is busy"}, status_code=503)
    except MetadataTimeout:
        return JSONResponse({"success": False, "error": "Metadata extraction timed out"}, status_code=504)
    except (MetadataError, OSError):
        return JSONResponse({"success": False, "error": "Could not fetch metadata"}, status_code=502)
    if rc == 0:
        return JSONResponse(stdout)
    return JSONResponse({"success": False}, status_code=404)


def summarize_video_info(info):
    """Distill a single yt-dlp metadata entry into a small, cheap-to-parse
    summary: just enough to answer "is this still available, and at what
    quality" without shipping the full formats/thumbnails/subtitles blob
    that /api/metadata returns.
    """
    if info.get("_type") == "playlist":
        entries = info.get("entries", [])
        return {
            "is_playlist": True,
            "title": info.get("title", ""),
            "video_count": len(entries),
        }

    formats = info.get("formats") or []
    best_format = None
    if formats:
        # yt-dlp orders formats worst-to-best; the last entry is the best one.
        f = formats[-1]
        best_format = {
            "format_id": f.get("format_id"),
            "ext": f.get("ext"),
            "resolution": f.get("resolution") or f.get("format_note"),
            "filesize": f.get("filesize") or f.get("filesize_approx"),
        }

    return {
        "is_playlist": False,
        "id": info.get("id"),
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "duration": info.get("duration"),
        "is_live": info.get("is_live"),
        "availability": info.get("availability"),
        "extractor": info.get("extractor"),
        "best_format": best_format,
    }


async def api_check_video(request):
    if request.headers.get("Content-Type") == "application/x-www-form-urlencoded":
        data = await request.form()
    else:
        data = await request.json()
    url = data.get("url", "").strip()
    if not url:
        return JSONResponse({"success": False, "error": "No URL provided"}, status_code=400)
    force_generic_extractor = data.get("force_generic_extractor", False)

    rc, metadata = request.app.state.ydlhandler.fetch_metadata(
        [url], force_generic_extractor=force_generic_extractor
    )
    if rc != 0:
        return JSONResponse({"success": False, "error": "Could not fetch video info"}, status_code=404)

    info = metadata[0] if metadata else {}
    return JSONResponse({"success": True, **summarize_video_info(info)})


async def api_playlist_info(request):
    if request.headers.get("Content-Type") == "application/x-www-form-urlencoded":
        data = await request.form()
    else:
        data = await request.json()
    url = data.get("url", "").strip()
    if not url:
        return JSONResponse({"success": False, "error": "No URL provided"}, status_code=400)

    rc, metadata = request.app.state.ydlhandler.fetch_metadata(
        [url], force_generic_extractor=False
    )
    if rc != 0:
        return JSONResponse({"success": False, "error": "Could not fetch playlist info"}, status_code=404)

    first = metadata[0] if metadata else {}
    if first.get("_type") != "playlist":
        return JSONResponse({"success": False, "error": "URL is not a playlist"}, status_code=400)

    entries = [
        {"title": e.get("title", e.get("url", "")), "url": e.get("url", "")}
        for e in first.get("entries", [])
        if e.get("url")
    ]

    return JSONResponse({
        "success": True,
        "title": first.get("title", ""),
        "playlist_id": first.get("id", ""),
        "video_count": len(entries),
        "entries": entries,
    })
