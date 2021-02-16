import json

SETTINGS = None

__all__ = ("get_settings",)


class Settings:
    log_file: str
    token: str
    show_summary_button: bool

    def __init__(self, env_file_name: str) -> None:
        with open(env_file_name) as f:
            content = json.loads(f.read())

        self.log_file = content["log_file"]
        self.token = content["token"]
        self.show_summary_button = content.get("show_summary_button", False)


def get_settings(env_file_name: str) -> Settings:
    global SETTINGS

    if SETTINGS:
        return SETTINGS

    SETTINGS = Settings(env_file_name)
    return SETTINGS
