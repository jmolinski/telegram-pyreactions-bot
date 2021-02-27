from typing import List, Optional, cast

import demoji

from telegram import Message as TelegramMessage

from constants import TEXTUAL_NORMALIZATION, TEXTUAL_REACTIONS
from settings import get_settings
from utils import (
    extract_custom_reaction,
    find_emojis_in_str,
    get_name_from_author_obj,
    is_disallowed_reaction,
    unique_list,
)


class MsgWrapper:
    msg: TelegramMessage

    def __init__(self, msg: TelegramMessage) -> None:
        self.msg = msg

    @property
    def is_reply(self) -> bool:
        return self.msg["reply_to_message"] is not None

    @property
    def msg_id(self) -> int:
        return cast(int, self.msg.message_id)

    @property
    def chat_id(self) -> int:
        return cast(int, self.msg.chat.id)

    @property
    def parent(self) -> Optional[int]:
        if self.is_reply:
            return cast(int, self.msg.reply_to_message.message_id)
        return None

    @property
    def is_reaction_msg(self) -> bool:
        return (
            self.is_simple_emoji_or_textual_reaction
            or self.is_many_reactions
            or self.is_custom_reaction
        )

    @property
    def is_simple_emoji_or_textual_reaction(self) -> bool:
        if is_disallowed_reaction(self.text):
            return False
        if len(self.text) == 1 or self.text in TEXTUAL_REACTIONS:
            return True

        found_reactions = find_emojis_in_str(self.text)
        return len(found_reactions) == 1 and not demoji.replace(self.text).strip()

    @property
    def is_many_reactions(self) -> bool:
        found_reactions = find_emojis_in_str(self.text)
        if any(is_disallowed_reaction(r) for r in found_reactions):
            return False

        return len(found_reactions) > 1 and not demoji.replace(self.text).strip()

    @property
    def is_custom_reaction(self) -> bool:
        if not get_settings().custom_text_reaction_allowed:
            return False

        return bool(extract_custom_reaction(self.text))

    @property
    def get_reactions_list(self) -> List[str]:
        if self.is_simple_emoji_or_textual_reaction:
            return [self.text]
        elif self.is_many_reactions:
            return unique_list(find_emojis_in_str(self.text))
        elif self.is_custom_reaction:
            return [cast(str, extract_custom_reaction(self.text))]
        else:
            raise ValueError("Can't extract reaction")

    @property
    def text(self) -> str:
        lower_text = self.msg.text_html.lower()
        if lower_text in TEXTUAL_NORMALIZATION:
            return TEXTUAL_NORMALIZATION[lower_text]

        return cast(str, self.msg.text_html.strip())

    @property
    def author(self) -> str:
        return get_name_from_author_obj(self.msg["from_user"])

    @property
    def author_id(self) -> int:
        return cast(int, self.msg.from_user.id)
