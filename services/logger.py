import logging
import os

import structlog


def setup_logger():
    """
    Configures structlog for structured logging.
    - Local: Pretty colored console output.
    - CI: Console output without colors (ANSI-free for grep).
    - Prod/Staging: JSON output for log aggregators.
    """
    env = os.environ.get("APP_ENV", "local").lower()

    # Shared processors
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if env == "ci":
        processors.append(structlog.dev.ConsoleRenderer(colors=False))
    elif env == "local":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return structlog.get_logger()


# Singleton logger instance
logger = setup_logger()
