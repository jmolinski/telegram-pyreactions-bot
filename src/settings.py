from __future__ import annotations

import json

from src import constants

SETTINGS: Settings

__all__ = (
    "get_settings",
    "configure_settings",
    "Settings",
)


class Settings:
    log_file: str
    token: str
    show_summary_button: bool
    disallowed_reactions: set[str]
    custom_text_reaction_allowed: bool
    anon_messages_allowed: bool
    anon_msg_prefix: str
    display_remove_ranking_button: bool
    silenced_chats: set[int]

    def __init__(self, env_file_name: str) -> None:
        with open(env_file_name) as f:
            content = json.loads(f.read())

        try:
            self.log_file = content["log_file"]
            self.token = content["token"]
        except Exception as e:
            raise ValueError("Missing required attributes in config file") from e
        self.show_summary_button = content.get("show_summary_button", True)
        self.disallowed_reactions = set(content.get("disallowed_reactions", []))
        self.custom_text_reaction_allowed = content.get(
            "custom_text_reaction_allowed", False
        )
        self.anon_messages_allowed = content.get("anon_messages_allowed", False)
        self.anon_msg_prefix = content.get("anon_msg_prefix", "")
        self.display_remove_ranking_button = content.get(
            "display_remove_ranking_button", False
        )
        self.silenced_chats = set(content.get("silenced_chats", []))


def configure_settings(env_file_name: str | None = None) -> None:
    env_file_name = env_file_name or constants.CONFIG_FILENAME

    global SETTINGS
    SETTINGS = Settings(env_file_name)


def get_settings() -> Settings:
    global SETTINGS
    if SETTINGS is None:
        configure_settings()

    return SETTINGS
