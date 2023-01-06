from __future__ import annotations


from typing import cast

from telegram import Message as TelegramMessage

from src.constants import (
    TEXTUAL_NORMALIZATION,
    TEXTUAL_REACTIONS,
    REACTIONS_IN_SINGLE_MSG_LIMIT,
)
from src.settings import get_settings
from src.utils import (
    extract_custom_reaction,
    extract_anon_message_text,
    find_emojis_in_str,
    get_name_from_author_obj,
    is_disallowed_reaction,
    unique_list,
    remove_emojis_from_text,
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
    def parent(self) -> int | None:
        if self.is_reply:
            assert self.msg.reply_to_message is not None
            return cast(int, self.msg.reply_to_message.message_id)
        return None

    @property
    def is_reaction_msg(self) -> bool:
        return (
            self.is_simple_emoji_or_textual_reaction
            or self.is_multiple_reactions
            or self.is_custom_reaction
        )

    @property
    def is_anon_message(self) -> bool:
        return get_settings().anon_messages_allowed and bool(
            extract_anon_message_text(self.text)
        )

    @property
    def is_simple_emoji_or_textual_reaction(self) -> bool:
        if is_disallowed_reaction(self.text):
            return False
        if len(self.text) == 1 or self.text in TEXTUAL_REACTIONS:
            return True

        found_reactions = find_emojis_in_str(self.text)
        return (
            len(found_reactions) == 1 and not remove_emojis_from_text(self.text).strip()
        )

    @property
    def is_multiple_reactions(self) -> bool:
        found_reactions = find_emojis_in_str(self.text)
        if any(is_disallowed_reaction(r) for r in found_reactions):
            return False

        return (
            REACTIONS_IN_SINGLE_MSG_LIMIT >= len(found_reactions) > 1
            and not remove_emojis_from_text(self.text).strip()
        )

    @property
    def is_custom_reaction(self) -> bool:
        if not get_settings().custom_text_reaction_allowed:
            return False

        return bool(extract_custom_reaction(self.text))

    @property
    def get_reactions_list(self) -> list[str]:
        if self.is_simple_emoji_or_textual_reaction:
            return [self.text]
        elif self.is_multiple_reactions:
            return unique_list(find_emojis_in_str(self.text))
        elif self.is_custom_reaction:
            return [cast(str, extract_custom_reaction(self.text))]
        else:
            raise ValueError("Can't extract reaction")

    @property
    def text(self) -> str:
        assert self.msg.text is not None
        lower_text = self.msg.text.lower()

        if lower_text in TEXTUAL_NORMALIZATION:
            return TEXTUAL_NORMALIZATION[lower_text]

        return cast(str, self.msg.text.strip())

    @property
    def author(self) -> str:
        return get_name_from_author_obj(cast(dict, self.msg["from_user"]))

    @property
    def author_id(self) -> int:
        assert self.msg.from_user is not None
        return cast(int, self.msg.from_user.id)
