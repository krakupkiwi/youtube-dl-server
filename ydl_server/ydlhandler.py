import logging
import os
import re
import shutil
import signal
import sys
from queue import Queue, Empty
from threading import Thread, Lock, Event
import io
import importlib
import json
from datetime import datetime
from subprocess import Popen, PIPE, STDOUT

from ydl_server.config import resolve_finished_file
from ydl_server.db import JobsDB, Job, Actions, JobType

logger = logging.getLogger(__name__)

YDL_MODULES = ["youtube_dl", "youtube_dlc", "yt_dlp"]


def get_ydl_website(ydl_module_name):
    try:
        import pip._internal.commands.show as pipshow
    except ModuleNotFoundError:
        logger.warning("Module not found, skipping get_ydl_website")
        return None

    info = list(pipshow.search_packages_info([ydl_module_name]))
    if len(info) < 1:
        return ""
    info = info[0]
    url = getattr(info, "homepage", None)
    if not url:
        urls = getattr(info, "project_urls", None)
        if urls:
            urls = {v.split(",")[0].strip(): v.split(",")[1].strip() for v in urls if "," in v}
            url = urls.get("Homepage") or urls.get("Documentation") or urls.get("Repository")
    return url


def read_proc_stdout(proc, strio):
    strio.write(proc.stdout.read1().decode())


DESTINATION_RE = re.compile(r"^\[download\] Destination: (.+)$", re.MULTILINE)

NOT_YET_AVAILABLE_RE = re.compile(r"(will begin in|premieres? in)\s", re.IGNORECASE)


def cleanup_partial_downloads(log_text):
    """Remove yt-dlp's .part temp file(s) for a download job that didn't
    complete successfully, matching the cleanup cut() already does on its
    own failure. Only ever touches the .part file, never the final output
    path itself, in case an earlier segment of a multi-file job already
    finished successfully before the job failed or was stopped.
    """
    for match in DESTINATION_RE.finditer(log_text):
        part_path = match.group(1).strip() + ".part"
        if os.path.isfile(part_path):
            try:
                os.remove(part_path)
            except OSError as e:
                logger.warning("Could not remove partial download %s: %s", part_path, e)


class YdlHandler:
    def import_ydl_module(self):
        ydl_module = None
        requested_module = os.environ.get("YOUTUBE_DL", "").replace("-", "_")
        if requested_module in YDL_MODULES:
            ydl_module = importlib.import_module(requested_module)
        else:
            for module in YDL_MODULES:
                try:
                    ydl_module = importlib.import_module(module)
                    break
                except ImportError:
                    pass
        if ydl_module is None:
            raise ImportError("No youtube_dl implementation found")

        self.ydl_module_name = ydl_module.__name__.replace("_", "-")
        self.ydl_website = get_ydl_website(self.ydl_module_name)

        # Resolve the executable so Popen can find it on all platforms (including
        # Windows where user-installed scripts may not be on the subprocess PATH).
        exe = shutil.which(self.ydl_module_name)
        if exe:
            self.ydl_cmd = [exe]
        else:
            # Fall back to running as a Python module: `python -m yt_dlp`
            self.ydl_cmd = [sys.executable, "-m", ydl_module.__name__]
            logger.warning(
                "'%s' not found on PATH, falling back to '%s'",
                self.ydl_module_name, " ".join(self.ydl_cmd),
            )

        self.ydls_version = os.environ.get("YDLS_VERSION", "")
        self.ydls_release_date = os.environ.get("YDLS_RELEASE_DATE", "")

        importlib.reload(ydl_module.version)
        importlib.reload(ydl_module.extractor)

        self.ydl_version = ydl_module.version.__version__
        self.ydl_extractors = [
            ie.IE_NAME
            for ie in ydl_module.extractor.list_extractors(
                self.app_config["ydl_options"].get("age-limit")
            )
            if ie._WORKING
        ]

    def __init__(self, app_config, jobshandler):
        self.queue = Queue()
        self.threads = []
        self.done = False
        self.ydl_module_name = None
        self.ydl_version = None
        self.ydl_extractors = []
        self.app_config = app_config
        self.jobshandler = jobshandler
        self.running_procs = {}
        self.running_procs_lock = Lock()

        self.app_config["ydl_last_update"] = datetime.now()

        self.import_ydl_module()

        logger.info("Using %s module", self.ydl_module_name)

    def stop_job(self, job_id):
        """Signal the live subprocess for job_id, if we still hold a handle to it.

        Stopping via our own tracked Popen handle (rather than a bare PID from the
        DB) avoids ever signalling an unrelated process after PID reuse.
        """
        with self.running_procs_lock:
            proc = self.running_procs.get(job_id)
        if proc is None:
            return False
        try:
            if os.name == "nt":
                # subprocess.Popen.send_signal only supports CTRL_C_EVENT/CTRL_BREAK_EVENT
                # (which require the child to be in a console process group we don't
                # create) or terminate() on Windows; plain SIGINT raises ValueError.
                proc.terminate()
            else:
                proc.send_signal(signal.SIGINT)
        except (ProcessLookupError, OSError):
            return False
        return True

    def start(self):
        self.download_workers_count = self.app_config["ydl_server"].get(
            "download_workers_count", 2
        )
        for i in range(self.download_workers_count):
            thread = Thread(target=self.worker, args=(i,))
            self.threads.append(thread)
            thread.start()
            logger.info("Started dl worker %i", i)

    def put(self, obj):
        self.queue.put(obj)

    def finish(self):
        self.done = True

    def worker(self, thread_id):
        db = JobsDB(readonly=True)
        while not self.done:
            try:
                job = self.queue.get(timeout=1)
            except Empty:
                continue
            job_detail = db.get_job_by_id(job.id)
            if not job_detail or job_detail["status"] == "Aborted":
                self.queue.task_done()
                continue
            job.status = Job.RUNNING
            self.jobshandler.put((Actions.SET_STATUS, (job.id, job.status)))
            self.queue.task_done()
            output = io.StringIO()
            try:
                if job.type == JobType.YDL_DOWNLOAD:
                    self.download(job, {"format": job.format}, output)
                elif job.type == JobType.FFMPEG_CUT:
                    self.cut(job, output)
            except Exception as e:
                job.status = Job.FAILED
                job.log = "Error during download task:\n{}:\n\t{}".format(
                    type(e).__name__, str(e)
                )
                logger.exception("Error during download task for job %s", job.id)
            self.jobshandler.put((Actions.UPDATE, job))

    def get_format_and_profile(self, format_string):
        fmt, audio, profile, aliases = None, None, None, []
        for s in format_string.split(","):
            if s.startswith("profile/"):
                profile = s
            elif s.startswith("alias/"):
                aliases.append(s)
            elif s.startswith("audio/") or s.startswith("bestaudio/"):
                audio = s
            else:
                fmt = s
        return fmt, audio, profile, aliases

    def get_profile(self, profile_str):
        if not profile_str:
            return {}
        profile_name = "/".join(profile_str.split("/")[1:])
        profile = self.app_config.get("profiles", {}).get(profile_name, {}).get('ydl_options')
        if not profile:
            raise Exception("Unknown profile ", profile_str)
        return profile

    def get_aliases(self, alias_strs):
        options = {}
        for alias_str in alias_strs:
            alias_name = "/".join(alias_str.split("/")[1:])
            alias = self.app_config.get("aliases", {}).get(alias_name, {}).get("ydl_options")
            if not alias:
                raise Exception("Unknown alias ", alias_str)
            options.update(alias)
        return options

    def get_extractor_options(self, extractor_name):
        """Look up per-extractor default ydl_options (config's extractor_options section).

        These apply as defaults only - an explicit format/profile/alias/output
        choice already resolved onto ydl_opts always takes precedence, since
        the caller merges these in underneath, not over, the existing options.
        """
        if not extractor_name:
            return {}
        return self.app_config.get("extractor_options", {}).get(
            extractor_name.lower(), {}
        ).get("ydl_options", {})

    def mark_not_yet_available(self, job):
        """Flag a job as failed because the video isn't available yet (an
        upcoming premiere/live event), rather than a real failure. JobsHandler's
        background sweep uses this marker to auto-retry the job later instead
        of leaving it permanently failed.
        """
        job.status = Job.FAILED
        extra_params = dict(job.extra_params or {})
        extra_params["not_yet_available"] = True
        extra_params.setdefault("auto_retry_count", 0)
        job.extra_params = extra_params
        logger.info(
            "Job %s not yet available (scheduled/upcoming); will auto-retry later", job.id
        )

    def get_ydl_options(self, ydl_config, request_options):
        ydl_config = ydl_config.copy()
        req_format, req_audio, req_profile, req_aliases = self.get_format_and_profile(request_options.get("format"))

        profile = self.get_profile(req_profile)
        aliases = self.get_aliases(req_aliases)
        if profile:
            req_format = profile.get("format") if req_format is None else req_format
        if aliases:
            req_format = aliases.get("format") if req_format is None else req_format

        if req_audio is not None and req_format is None:
            ydl_config.update({"extract-audio": None})
            ydl_config.update({"audio-format": req_audio.split("/")[-1]})

        if req_format is not None:
            if req_format == "video/best":
                req_format = "video/bestvideo"
            if req_format.startswith("video/"):
                # youtube-dl downloads BEST video and audio by default
                if req_format != "video/best":
                    req_format = req_format.split("/")[-1]
            if req_audio is not None:
                req_format = req_format + "+" + req_audio.split("/")[-1]
            else:
                req_format = req_format + "+bestaudio/best"
            ydl_config.update({"format": req_format})

        if req_format is None and req_audio is None:
            ydl_config.update({"format": "video/best"})

        if profile:
            profile = {k: v for k, v in profile.items() if k != "format"}
            ydl_config.update(profile)
        if aliases:
            aliases = {k: v for k, v in aliases.items() if k != "format"}
            ydl_config.update(aliases)
        return ydl_config

    def download_log_update(self, job, proc, strio, stop_event):
        while not stop_event.is_set():
            read_proc_stdout(proc, strio)
            job.log = Job.clean_logs(strio.getvalue())
            self.jobshandler.put((Actions.SET_LOG, (job.id, job.log)))
            stop_event.wait(3)

    def fetch_metadata(self, url, force_generic_extractor=False):
        ydl_opts = self.app_config.get("ydl_options", {})
        extra_opts = ["-J", "--flat-playlist"]
        if force_generic_extractor:
            extra_opts.append("--force-generic-extractor")
        cmd = self.get_ydl_full_cmd(ydl_opts, url, extra_opts)

        proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
        stdout, stderr = proc.communicate()
        if proc.wait() != 0:
            return -1, stderr.decode()

        return 0, [json.loads(s) for s in stdout.decode().strip().split("\n")]

    def get_ydl_full_cmd(self, opt_dict, url, extra_opts=None):
        cmd = list(self.ydl_cmd)
        if opt_dict is not None:
            for key, val in opt_dict.items():
                if isinstance(val, bool) and not val:
                    continue
                cmd.append("--{}".format(key))
                if val is not None and not isinstance(val, bool):
                    cmd.append(str(val))
        if extra_opts is not None and isinstance(extra_opts, list):
            cmd.extend(extra_opts)
        cmd.append("--")
        cmd.extend(url)
        return cmd

    def download(self, job, request_options, output):
        ydl_opts = self.get_ydl_options(
            self.app_config.get("ydl_options", {}), request_options
        )
        extra_opts = []
        force_generic = getattr(job, "force_generic_extractor", False)
        if force_generic:
            extra_opts.append("--force-generic-extractor")
        cmd = self.get_ydl_full_cmd(ydl_opts, job.url, extra_opts)

        rc, metadata = self.fetch_metadata(job.url, force_generic_extractor=force_generic)
        if rc != 0:
            job.log = Job.clean_logs(metadata)
            if NOT_YET_AVAILABLE_RE.search(metadata):
                self.mark_not_yet_available(job)
                return
            job.status = Job.FAILED
            logger.error("Error in metadata fetching process:\n%s", job.log)
            raise Exception(job.log)

        if metadata and metadata[0].get("live_status") == "is_upcoming":
            job.log = Job.clean_logs(
                "This video is not available yet (scheduled/upcoming). Will retry automatically."
            )
            self.mark_not_yet_available(job)
            return

        title = ", ".join(
            [md.get("title", job.url[i]) for i, md in enumerate(metadata)]
        )
        self.jobshandler.put((Actions.SET_NAME, (job.id, title)))

        extractor_opts = self.get_extractor_options(metadata[0].get("extractor"))
        if extractor_opts:
            ydl_opts = {**extractor_opts, **ydl_opts}

        if metadata[0].get("_type") == "playlist" or len(metadata) > 1:
            ydl_opts.update(
                {
                    "output": self.app_config["ydl_server"].get(
                        "output_playlist", ydl_opts.get("output")
                    )
                }
            )
        elif job.extra_params.get("title") and ydl_opts.get("output"):
            output_template_parts = ydl_opts.get("output").split("/")
            output_template = '/'.join(output_template_parts[:-1]) + f"/{job.extra_params.get("title")}.%(ext)s"
            ydl_opts.update(
                {
                    "output": output_template,
                }
            )

        cmd = self.get_ydl_full_cmd(ydl_opts, job.url, extra_opts)

        try:
            fmt_proc = Popen(
                self.get_ydl_full_cmd(ydl_opts, job.url, extra_opts + ["--simulate", "--print", "%(format)s"]),
                stdout=PIPE, stderr=PIPE
            )
            fmt_stdout, _ = fmt_proc.communicate()
            if fmt_proc.returncode == 0 and fmt_stdout.strip():
                output.write("[format] {}\n".format(fmt_stdout.decode().strip()))
        except Exception as e:
            logger.warning("Error looking up format: %s", e)

        proc = Popen(cmd, stdout=PIPE, stderr=STDOUT)
        self.jobshandler.put((Actions.SET_PID, (job.id, proc.pid)))
        with self.running_procs_lock:
            self.running_procs[job.id] = proc
        stop_log_thread = Event()
        stdout_thread = Thread(
            target=self.download_log_update, args=(job, proc, output, stop_log_thread)
        )
        stdout_thread.start()

        try:
            rc = proc.wait()
        finally:
            with self.running_procs_lock:
                self.running_procs.pop(job.id, None)

        # Stop and join the log-tailing thread before doing our own final
        # read, so the two threads never call proc.stdout.read1() at once.
        stop_log_thread.set()
        stdout_thread.join()
        read_proc_stdout(proc, output)
        job.log = Job.clean_logs(output.getvalue())
        if rc == 0:
            job.status = Job.COMPLETED
        else:
            job.status = Job.FAILED
            cleanup_partial_downloads(output.getvalue())
            logger.error("Error in download process (RC=%s):\n%s", rc, output.getvalue())

    def cut(self, job, output):
        params = job.extra_params
        src = resolve_finished_file(job.url[0])
        if src is None:
            raise Exception("Invalid source file path")
        if not os.path.isfile(src):
            raise Exception("Source file not found: %s" % job.url[0])
        dst = os.path.join(os.path.dirname(src), params["output"])

        cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-y", "-ss", str(params.get("start") or "0")]
        if params.get("end"):
            cmd.extend(["-to", str(params["end"])])
        cmd.extend(["-i", src])
        if params.get("mode", "fast") == "fast":
            cmd.extend(["-c", "copy", "-avoid_negative_ts", "make_zero"])
        cmd.append(dst)

        output.write("[cut] {}\n".format(" ".join(cmd)))
        proc = Popen(cmd, stdout=PIPE, stderr=STDOUT)
        self.jobshandler.put((Actions.SET_PID, (job.id, proc.pid)))
        with self.running_procs_lock:
            self.running_procs[job.id] = proc
        stop_log_thread = Event()
        stdout_thread = Thread(
            target=self.download_log_update, args=(job, proc, output, stop_log_thread)
        )
        stdout_thread.start()

        try:
            rc = proc.wait()
        finally:
            with self.running_procs_lock:
                self.running_procs.pop(job.id, None)

        stop_log_thread.set()
        stdout_thread.join()
        read_proc_stdout(proc, output)
        job.log = Job.clean_logs(output.getvalue())
        if rc == 0:
            job.status = Job.COMPLETED
        else:
            job.status = Job.FAILED
            if os.path.isfile(dst):
                os.remove(dst)
            logger.error("Error in cut process (RC=%s):\n%s", rc, output.getvalue())
        stdout_thread.join()

    def resume_pending(self):
        db = JobsDB(readonly=False)
        jobs = db.get_jobs_with_logs(self.app_config["ydl_server"].get("max_log_entries", 100))
        not_endeds = [
            job
            for job in jobs
            if job["status"] == "Pending" or job["status"] == "Running"
        ]
        for pending in not_endeds:
            job = Job(
                pending["name"],
                Job.PENDING,
                "Queue stopped",
                int(pending["type"]),
                pending["format"],
                pending["urls"],
                extra_params=pending.get("extra_params", {})
            )
            job.id = pending["id"]
            job.force_generic_extractor = pending.get("force_generic_extractor", False)
            self.jobshandler.put((Actions.RESUME, job))

    def join(self):
        for thread in self.threads:
            thread.join()
