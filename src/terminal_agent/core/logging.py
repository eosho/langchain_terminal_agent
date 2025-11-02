"""
Logging configuration for the Terminal Agent.
"""

import logging
import logging.config


def setup_logging(default_level: int = logging.INFO) -> None:
    """Configure structured logging for the entire package.

    This function sets up a root logger using Python's ``logging.config``
    dictionary configuration. It ensures consistent formatting across
    all modules and suppresses duplicate loggers.

    Example:
        ```python
        from terminal_agent.core.logging import setup_logging

        setup_logging()
        logger = logging.getLogger(__name__)
        logger.info("Logging initialized successfully.")
        ```

    Args:
        default_level: The default log level for the root logger.
            Typically one of:
            - ``logging.DEBUG``
            - ``logging.INFO`` (default)
            - ``logging.WARNING``
            - ``logging.ERROR``
            - ``logging.CRITICAL``

    Returns:
        None
    """
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "[%(asctime)s] - [%(levelname)s] - %(name)s: %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": "INFO",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": default_level,
        },
    }

    logging.config.dictConfig(logging_config)
