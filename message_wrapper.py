from typing import Optional

import demoji
from telegram import Message as TelegramMessage

from constants import TEXTUAL_NORMALIZATION, TEXTUAL_REACTIONS
from utils import find_emojis_in_str, get_name_from_author_obj, unique_list


class MsgWrapper:
    def __init__(self, msg: TelegramMessage) -> None:
        self.msg = msg

    @property
    def is_reply(self) -> bool:
        return self.msg["reply_to_message"] is not None

    @property
    def msg_id(self) -> int:
        return self.msg["message_id"]

    @property
    def chat_id(self) -> int:
        return self.msg["chat"]["id"]

    @property
    def parent(self) -> Optional[int]:
        if self.is_reply:
            return self.msg["reply_to_message"]["message_id"]
        return None

    @property
    def is_reaction(self) -> bool:
        if self.text is None:
            return False
        if len(self.text) == 1 or self.text in TEXTUAL_REACTIONS:
            return True

        return (
            len(find_emojis_in_str(self.text)) == 1
            and not demoji.replace(self.text).strip()
        )

    @property
    def is_many_reactions(self):
        return (
            len(find_emojis_in_str(self.text)) > 1
            and not demoji.replace(self.text).strip()
        )

    @property
    def get_reactions_set(self):
        if not self.is_many_reactions:
            return {self.text}

        return unique_list(find_emojis_in_str(self.text))

    @property
    def text(self) -> str:
        lower_text = self.msg["text"].lower()
        if lower_text in TEXTUAL_NORMALIZATION:
            return TEXTUAL_NORMALIZATION[lower_text]

        return self.msg["text"].strip()

    @property
    def author(self) -> str:
        return get_name_from_author_obj(self.msg["from_user"])

    @property
    def author_id(self) -> str:
        return self.msg["from_user"]["id"]
