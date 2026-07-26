import logging
from datetime import UTC, datetime
from logging.config import dictConfig


class UTCFormatter(logging.Formatter):
    def formatTime(
        self,
        record: logging.LogRecord,
        datefmt: str | None = None,
    ) -> str:
        value = datetime.fromtimestamp(record.created, tz=UTC)
        if datefmt:
            return value.strftime(datefmt)
        return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def setup_logging(
    log_level: str = "INFO",
    service_name: str = "executor-service",
) -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": UTCFormatter,
                    "fmt": (
                        "%(asctime)s "
                        f"[{service_name}] "
                        "%(levelname)s %(name)s - %(message)s"
                    ),
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {
                "level": log_level.upper(),
                "handlers": ["console"],
            },
            "loggers": {
                "redis": {"level": "WARNING"},
                "httpx": {"level": "WARNING"},
                "websockets": {"level": "WARNING"},
            },
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

