"""Main entry point for the SmartReco Agent server.

Validates configuration and starts Uvicorn. Actual DB pool lifecycle is
handled inside `api.py`'s lifespan context, not here, so that the app object
remains importable (and testable) without a running server.
"""

import sys
from typing import NoReturn

import uvicorn

from smartreco_agent.src.api import app
from smartreco_agent.src.core.exceptions.exceptions import (
    AppException,
    AppExceptionCode,
)
from smartreco_agent.src.settings import settings
from smartreco_agent.src.settings import validate_config as validate_config_func
from smartreco_agent.utils.pylogger import get_python_logger, get_uvicorn_log_config

logger = get_python_logger(settings.PYTHON_LOG_LEVEL)


def validate_and_initialize_config() -> None:
    """Validate configuration settings before the server starts accepting traffic.

    Raises:
        AppException: If required configuration values are missing or invalid.
    """
    try:
        validate_config_func(settings)
        logger.info("Configuration validation passed")
    except AppException:
        raise
    except Exception:
        raise AppException(
            "Configuration validation failed",
            AppExceptionCode.CONFIGURATION_VALIDATION_ERROR,
        )


def handle_startup_error(error: Exception, context: str = "server startup") -> NoReturn:
    """Log a startup error with the right severity and exit with a matching code."""
    if isinstance(error, (ValueError, AppException)):
        logger.critical(f"Configuration error during {context}: {error}")
        sys.exit(1)
    elif isinstance(error, KeyboardInterrupt):
        logger.info("Server startup interrupted by user")
        sys.exit(0)
    elif isinstance(error, PermissionError):
        logger.critical(f"Permission error during {context}: {error}")
        sys.exit(1)
    elif isinstance(error, ConnectionError):
        logger.critical(f"Connection error during {context}: {error}")
        sys.exit(1)
    else:
        logger.critical(f"Unexpected error during {context}: {error}", exc_info=True)
        sys.exit(1)


def main() -> None:
    """Validate config and run the SmartReco Agent server under Uvicorn."""
    try:
        validate_and_initialize_config()

        logger.info(
            f"Starting SmartReco Agent server on {settings.AGENT_HOST}:{settings.AGENT_PORT}"
        )

        uvicorn.run(
            app=app,
            host=settings.AGENT_HOST,
            port=settings.AGENT_PORT,
            log_config=get_uvicorn_log_config(settings.PYTHON_LOG_LEVEL),
        )

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down")
    except Exception as e:
        handle_startup_error(e, "server startup")
    finally:
        logger.info("SmartReco Agent server shutting down")


def run() -> None:
    """Run `main` with a final safety-net exit handler."""
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error("Server failed to start", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
