import logging
import time
from datetime import datetime
from queue import Queue, Empty
from threading import Thread
from ydl_server.db import Actions, Job, JobsDB, JobType

logger = logging.getLogger(__name__)

AUTO_RETRY_SWEEP_INTERVAL_SECONDS = 60
AUTO_RETRY_DELAY_SECONDS = 30 * 60
AUTO_RETRY_MAX_ATTEMPTS = 20


class JobsHandler:
    def __init__(self, app_config):
        self.queue = Queue()
        self.thread = None
        self.done = False
        self.app_config = app_config
        self._last_auto_retry_sweep = 0.0

    def start(self, dl_queue):
        self.thread = Thread(target=self.worker, args=(dl_queue,))
        self.thread.start()

    def stop(self):
        self.done = True

    def put(self, obj):
        self.queue.put(obj)

    def finish(self):
        self.done = True

    def worker(self, dl_queue):
        db = JobsDB(readonly=False)
        while not self.done:
            try:
                action, job = self.queue.get(timeout=1)
            except Empty:
                self._maybe_auto_retry_scheduled_jobs(db, dl_queue)
                continue
            if action == Actions.PURGE_LOGS:
                if db.purge_jobs():
                    db.vacuum()
            elif action == Actions.INSERT:
                if db.clean_old_jobs(
                        self.app_config["ydl_server"].get("max_log_entries", 100) - 1
                    ):
                    db.vacuum()
                db.insert_job(job)
                dl_queue.put(job)
            elif action == Actions.UPDATE:
                db.update_job(job)
            elif action == Actions.RESUME:
                db.update_job(job)
                dl_queue.put(job)
            elif action == Actions.SET_NAME:
                job_id, name = job
                db.set_job_name(job_id, name)
            elif action == Actions.SET_LOG:
                job_id, log = job
                db.set_job_log(job_id, log)
            elif action == Actions.SET_STATUS:
                job_id, status = job
                db.set_job_status(job_id, status)
            elif action == Actions.SET_PID:
                job_id, pid = job
                db.set_job_pid(job_id, pid)
            elif action == Actions.CLEAN_LOGS:
                if db.clean_old_jobs():
                    db.vacuum()
            elif action == Actions.DELETE_LOG_SAFE:
                if db.delete_job_safe(job["id"]):
                    db.vacuum()
            elif action == Actions.DELETE_LOG:
                if db.delete_job(job["id"]):
                    db.vacuum()
            self.queue.task_done()

    def _maybe_auto_retry_scheduled_jobs(self, db, dl_queue):
        now = time.monotonic()
        if now - self._last_auto_retry_sweep < AUTO_RETRY_SWEEP_INTERVAL_SECONDS:
            return
        self._last_auto_retry_sweep = now

        for job_dict in db.get_failed_jobs_for_auto_retry():
            try:
                last_update = datetime.strptime(job_dict["last_update"], "%Y-%m-%d %H:%M:%S")
            except (TypeError, ValueError):
                continue
            age_seconds = (datetime.utcnow() - last_update).total_seconds()
            if age_seconds < AUTO_RETRY_DELAY_SECONDS:
                continue

            extra_params = job_dict["extra_params"]
            retry_count = extra_params.get("auto_retry_count", 0)
            if retry_count >= AUTO_RETRY_MAX_ATTEMPTS:
                continue

            new_extra_params = dict(extra_params)
            new_extra_params.pop("not_yet_available", None)
            new_extra_params["auto_retry_count"] = retry_count + 1

            new_job = Job(
                job_dict["name"], Job.PENDING, "", JobType.YDL_DOWNLOAD,
                job_dict["format"], job_dict["urls"], extra_params=new_extra_params,
            )
            new_job.force_generic_extractor = job_dict["force_generic_extractor"]

            db.delete_job_safe(job_dict["id"])
            if db.clean_old_jobs(self.app_config["ydl_server"].get("max_log_entries", 100) - 1):
                db.vacuum()
            db.insert_job(new_job)
            dl_queue.put(new_job)
            logger.info(
                "Auto-retrying scheduled job %s (attempt %d)", job_dict["id"], retry_count + 1
            )

    def join(self):
        if self.thread is not None:
            return self.thread.join()
