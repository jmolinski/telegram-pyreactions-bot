from settings import Settings
import logging

__all__ = ("get_logger",)

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
