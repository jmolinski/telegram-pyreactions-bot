from __future__ import annotations

from src import constants
from typing import Any
from src.db import get_conn
from src.logger import get_default_logger
from src.message_wrapper import MsgWrapper
from src.utils import hash_string
from telegram import (
    Bot,
    Update,
    InlineKeyboardMarkup,
)
from telegram.ext import CallbackContext


def make_msg_id(msg_id: int, chat_id: int) -> int:
    return hash_string(f"{abs(chat_id)}:{abs(msg_id)}")


def send_message(
    bot: Bot,
    chat_id: int,
    parent_id: int | None = None,
    markup: InlineKeyboardMarkup | None = None,
    text: str | None = None,
    save_to_db: bool = False,
    is_ranking: bool = False,
    is_bot_reaction: bool = False,
    is_anon: bool = False,
    **kwargs: Any,
) -> MsgWrapper:
    if text is None:
        text = constants.EMPTY_MSG

    base_args = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }

    if parent_id:
        base_args["reply_to_message_id"] = parent_id
    if markup:
        base_args["reply_markup"] = markup

    if kwargs:
        base_args.update(kwargs)

    sent_msg = MsgWrapper(bot.send_message(**base_args))

    if save_to_db:
        save_message_to_db(
            sent_msg,
            is_ranking=is_ranking,
            is_bot_reaction=is_bot_reaction,
            is_anon=is_anon,
        )

    return sent_msg


def send_reply(
    update: Update,
    context: CallbackContext,
    text: str,
    *,
    save_to_db: bool = False,
    is_ranking: bool = False,
    is_bot_reaction: bool = False,
    is_anon: bool = False,
    **kwargs: Any,
) -> MsgWrapper:
    parent_msg = MsgWrapper(update.message)
    reply_msg = send_message(
        context.bot,
        parent_msg.chat_id,
        parent_msg.msg_id,
        None,
        text=text,
        save_to_db=save_to_db,
        is_ranking=is_ranking,
        is_bot_reaction=is_bot_reaction,
        is_anon=is_anon,
        **kwargs,
    )

    return reply_msg


def save_message_to_db(
    msg: MsgWrapper,
    *,
    is_bot_reaction: bool = False,
    is_ranking: bool = False,
    is_anon: bool = False,
) -> None:
    get_default_logger().info("Savin message to db")
    sql = (
        "INSERT INTO message (id, original_id, author_id, author, chat_id, parent, is_bot_reaction, is_ranking, is_anon) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);"
    )
    with get_conn() as conn:
        conn.execute(
            sql,
            (
                make_msg_id(msg.msg_id, msg.chat_id),
                msg.msg_id,
                msg.author_id,
                msg.author,
                msg.chat_id,
                None if msg.parent is None else make_msg_id(msg.parent, msg.chat_id),
                is_bot_reaction,
                is_ranking,
                is_anon,
            ),
        )
