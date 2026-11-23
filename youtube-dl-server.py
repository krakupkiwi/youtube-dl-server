import logging
from contextlib import asynccontextmanager

import uvicorn
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from ydl_server.logging_config import configure_logging

configure_logging()

from ydl_server.config import app_config
from ydl_server.db import JobsDB
from ydl_server.jobshandler import JobsHandler
from ydl_server.middleware import APIKeyMiddleware
from ydl_server.routes import routes
from ydl_server.ydlhandler import YdlHandler

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    if app_config["ydl_server"].get("debug", False):
        logging.getLogger().setLevel(logging.DEBUG)

    JobsDB.init()

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            await run_in_threadpool(shutdown)

    middleware = [Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"])]
    api_key = app_config["ydl_server"].get("api_key")
    if api_key:
        middleware.append(Middleware(APIKeyMiddleware, api_key=api_key))
        logger.info("API key protection enabled for /api/ routes")

    app = Starlette(
        routes=routes,
        debug=app_config["ydl_server"].get("debug", False),
        middleware=middleware,
        lifespan=lifespan,
    )

    app.state.running = True
    app.state.jobshandler = JobsHandler(app_config)
    app.state.ydlhandler = YdlHandler(app_config, app.state.jobshandler)

    def shutdown():
        if not app.state.running:
            return
        logger.info("Shutting down...")
        app.state.running = False
        app.state.ydlhandler.shutdown()
        logger.info("Shutdown complete.")

    app.state.ydlhandler.start()
    logger.info("Started download threads")
    app.state.jobshandler.start(app.state.ydlhandler.queue)
    logger.info("Started jobs manager thread")

    app.state.ydlhandler.resume_pending()

    try:
        uvicorn.run(
            app,
            host=app_config["ydl_server"].get("host"),
            port=app_config["ydl_server"].get("port"),
            log_level=("debug" if app_config["ydl_server"].get("debug", False) else "info"),
            forwarded_allow_ips=app_config["ydl_server"].get("forwarded_allow_ips", None),
            proxy_headers=app_config["ydl_server"].get("proxy_headers", True),
            timeout_graceful_shutdown=app_config["ydl_server"].get("shutdown_timeout", 5),
        )
    finally:
        shutdown()
