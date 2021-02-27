import json

from typing import Optional, Set

import constants

SETTINGS = None

__all__ = ("get_settings",)


class Settings:
    log_file: str
    token: str
    show_summary_button: bool
    disallowed_reactions: Set[str]

    def __init__(self, env_file_name: str) -> None:
        with open(env_file_name) as f:
            content = json.loads(f.read())

        self.log_file = content["log_file"]
        self.token = content["token"]
        self.show_summary_button = content.get("show_summary_button", False)
        self.disallowed_reactions = set(content.get("disallowed_reactions", []))


def get_settings(env_file_name: Optional[str] = None) -> Settings:
    global SETTINGS

    if SETTINGS:
        return SETTINGS

    env_file_name = env_file_name or constants.CONFIG_FILENAME
    SETTINGS = Settings(env_file_name)
    return SETTINGS
