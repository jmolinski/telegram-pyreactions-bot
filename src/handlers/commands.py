from __future__ import annotations

import time

from telegram import (
    ParseMode,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import CallbackContext

from src import constants

from src.db import get_conn
from src.message_wrapper import MsgWrapper
from src.settings import get_settings
from src.utils import _escape_markdown_v2

from src.handlers.common import send_message, save_message_to_db


DEFAULT_RANKING_DAYS = 7
DEFAULT_MOST_REACTED_MSGS_TO_SHOW = 10
WAIT_TIME_BETWEEN_MESSAGES_SECONDS = 0.5


def handler_show_ranking(update: Update, context: CallbackContext) -> None:
    assert update.message is not None

    try:
        days = DEFAULT_RANKING_DAYS
        if context.args:
            days = int(context.args[0])
            if days < 1:
                update.message.reply_text("Days argument must be >= 1.")
                return
    except (IndexError, ValueError):
        update.message.reply_text("Usage: " + COMMANDS["ranking"]["usage"])
        return

    min_timestamp = time.time_ns() - days * (24 * 60 * 60 * 10**9)
    with get_conn() as conn:
        reactions_received = list(
            conn.execute(
                "SELECT author_id, sum(msg_reactions.cnt) "
                "from message "
                "inner join (select parent, count(*) as cnt from reaction where timestamp > ? group by parent) as msg_reactions "
                "on message.id=msg_reactions.parent "
                "where chat_id=? "
                "group by message.author_id "
                "order by sum(msg_reactions.cnt) desc",
                (
                    min_timestamp,
                    update.message.chat_id,
                ),
            ).fetchall()
        )

        reactions_given = list(
            conn.execute(
                "SELECT author_id, count(*) "
                "from reaction "
                "inner join (select id, chat_id from message) as reaction_msg "
                "on reaction_msg.id=reaction.parent "
                "where timestamp > ? and reaction_msg.chat_id = ?"
                "group by reaction.author_id "
                "order by count(*) desc",
                (
                    min_timestamp,
                    update.message.chat_id,
                ),
            ).fetchall()
        )

    text = f"Reactions received in the last {days} days\n"
    with get_conn() as conn:
        for i, (user_id, cnt) in enumerate(reactions_received, start=1):
            username = conn.execute(
                "SELECT author from message where author_id=? LIMIT 1",
                (user_id,),
            ).fetchone()[0]

            text += f"{i}. {username}: {cnt}\n"

    text += f"\nReactions given in the last {days} days\n"
    with get_conn() as conn:
        for i, (user_id, cnt) in enumerate(reactions_given, start=1):
            username = conn.execute(
                "SELECT author from reaction where author_id=? LIMIT 1",
                (user_id,),
            ).fetchone()[0]

            text += f"{i}. {username}: {cnt}\n"

    parent_msg = MsgWrapper(update.message)
    ranking_msg = send_message(
        context.bot, parent_msg.chat_id, parent_msg.msg_id, None, text=text
    )
    save_message_to_db(ranking_msg, is_ranking=True)

    if get_settings().display_remove_ranking_button:
        delete_button = InlineKeyboardButton(
            "delete ranking", callback_data=f"{ranking_msg.msg_id}__delete"
        )
        context.bot.edit_message_reply_markup(
            chat_id=ranking_msg.chat_id,
            message_id=ranking_msg.msg_id,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[delete_button]]),
        )


def handler_show_messages_with_most_reactions(
    update: Update, context: CallbackContext
) -> None:
    assert update.message is not None
    assert context.args is not None

    days = DEFAULT_RANKING_DAYS
    requested_messages_cnt = DEFAULT_MOST_REACTED_MSGS_TO_SHOW
    try:
        if context.args:
            days = int(context.args[0])
            if days < 1:
                update.message.reply_text("Days argument must be >= 1.")
                return
        if len(context.args) > 1:
            requested_messages_cnt = int(context.args[1])
            if requested_messages_cnt < 1 or requested_messages_cnt > 30:
                update.message.reply_text(
                    "Number of messages must be between 1 and 30."
                )
                return
    except ValueError:
        update.message.reply_text("Usage: " + COMMANDS["top"]["usage"])
        return

    min_timestamp = time.time_ns() - days * (24 * 60 * 60 * 10**9)

    query_parts = [
        "select message.author_id, message.original_id, count(*) as c from message "
        "inner join reaction "
        "on message.id = reaction.parent "
        "where reaction.timestamp > ? "
        "and message.chat_id = ? ",
        "group by message.id order by c desc ",
        "limit ?",
    ]
    query_arguments: list[int | str] = [
        min_timestamp,
        update.message.chat_id,
        requested_messages_cnt,
    ]

    if len(context.args) > 2:
        user = context.args[2]
        query_parts.insert(1, "and message.author = ?")
        query_arguments.insert(2, user)

    with get_conn() as conn:
        reactions_received = conn.execute(
            "".join(query_parts), query_arguments
        ).fetchall()

    wait_time_between_messages = WAIT_TIME_BETWEEN_MESSAGES_SECONDS
    parent_msg = MsgWrapper(update.message)
    for i, (user_id, message_id, cnt) in enumerate(reactions_received, start=1):
        time.sleep(wait_time_between_messages)
        send_message(
            context.bot, parent_msg.chat_id, message_id, None, text=f"{i}. {cnt}"
        )


def get_help_features() -> str:
    disallowed_reactions = ", ".join(
        f"`{reaction}`" for reaction in get_settings().disallowed_reactions
    )
    features = [
        (
            "Reply to a message, or to the existing bot reply to this message with only emojis to react.",
            True,
        ),
        (
            "Reply with a single character to react with it.",
            True,
        ),
        (
            "To add a reaction with a custom text reply in the format of: `!react <text>`, or `!r <text>`",
            get_settings().custom_text_reaction_allowed,
        ),
        (
            "To send an anonymous message with a custom text prefix it with: `!anon <text>`, or `!a <text>`",
            get_settings().anon_messages_allowed,
        ),
        (
            rf"Banned reactions are: {disallowed_reactions}, `+n`, `-n` \(where `n != 1`\).",
            get_settings().disallowed_reactions,
        ),
        ("Reply with `+1` to upvote or `-1` to downvote.", True),
        ("Click on an already added reaction to also react with it.", True),
        (
            "If you have already reacted you can click on this reaction to remove it.",
            True,
        ),
        (
            rf"Click on the last reaction *\(*{constants.INFORMATION_EMOJI}*\)* to toggle reactions summary.",
            get_settings().show_summary_button,
        ),
    ]

    enabled_features = (f for f, enabled in features if enabled)
    return "\n".join(
        f"{i}. {feature}" for i, feature in enumerate(enabled_features, start=1)
    )


def get_help_for_commands() -> str:
    return "\n".join(
        f"{i}. `{command}` - {data['description']}\nUsage: `{data['usage']}`"
        for i, (command, data) in enumerate(COMMANDS.items(), start=1)
    )


def _get_help_text() -> str:
    features_txt = get_help_features()
    res = f"""*Features:*
{features_txt}

*Setup:*
1. Add the bot to the conversation.
2. Give it admin permissions. You can limit its permissions to only delete messages.

*Commands:*
{get_help_for_commands()}

*For further support:*
[Github Repository](https://github.com/jmolinski/telegram-pyreactions-bot/)
"""
    return _escape_markdown_v2(res)


def handler_help(update: Update, context: CallbackContext) -> None:
    help_text = _get_help_text()

    assert update.message is not None
    update.message.reply_text(
        help_text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True
    )


COMMANDS = {
    "help": {
        "description": "Show this help message.",
        "usage": "/help",
        "handler": handler_help,
    },
    "ranking": {
        "description": "Show the ranking of users ordered by the received and given reactions.",
        "usage": "/ranking [days]",
        "handler": handler_show_ranking,
    },
    "top": {
        "description": "Show the most reacted messages.",
        "usage": "/top [days] [number of messages] [@author]",
        "handler": handler_show_messages_with_most_reactions,
    },
}
