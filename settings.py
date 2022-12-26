import json

import constants

SETTINGS = None

__all__ = (
    "get_settings",
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


def get_settings(env_file_name: str | None = None) -> Settings:
    global SETTINGS

    if SETTINGS:
        return SETTINGS

    env_file_name = env_file_name or constants.CONFIG_FILENAME
    SETTINGS = Settings(env_file_name)
    return SETTINGS
