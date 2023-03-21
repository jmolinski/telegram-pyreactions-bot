import logging

from src.settings import Settings, get_settings

__all__ = (
    "get_logger",
    "get_default_logger",
)

LOGGER = None


def get_logger(settings: Settings) -> logging.Logger:
    global LOGGER

    if LOGGER:
        return LOGGER

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(settings.log_file), logging.StreamHandler()],
    )

    LOGGER = logging.getLogger("pyreactions_bot")
    return LOGGER


def get_default_logger() -> logging.Logger:
    return get_logger(get_settings())
