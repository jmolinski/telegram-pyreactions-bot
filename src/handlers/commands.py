from __future__ import annotations
from abc import ABC
import time
from typing import Callable, Type
import telegram.error
from telegram import (
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

from src.handlers.common import send_message, send_reply


DEFAULT_RANKING_DAYS = 7
DEFAULT_MOST_REACTED_MSGS_TO_SHOW = 10
WAIT_TIME_BETWEEN_MESSAGES_SECONDS = 0.5
MAX_TIMESPAN_DAYS = 10 * 365
MAX_TOP_MESSAGES_COUNT = 30
NS_IN_ONE_DAY = 24 * 60 * 60 * 10**9


class UsageError(Exception):
    pass


class CommandHandler(ABC):
    description: str
    usage: str
    _handler: Callable[[Update, CallbackContext], None]

    @classmethod
    def name(cls) -> str:
        return cls.__name__.lower().replace("commandhandler", "")

    @classmethod
    def handler(cls, update: Update, context: CallbackContext) -> None:
        try:
            cls._handler(update, context)
        except UsageError as e:
            if e.args:
                error_message = f"Usage error: {', '.join(e.args)}"
            else:
                error_message = "Usage: " + cls.usage

            send_reply(update, context, error_message, save_to_db=True)


class RankingCommandHandler(CommandHandler):
    description = (
        "Show the ranking of users ordered by the received and given reactions."
    )
    usage = "/ranking [days]"

    @staticmethod
    def _handler(update: Update, context: CallbackContext) -> None:
        assert update.message is not None

        try:
            days = DEFAULT_RANKING_DAYS
            if context.args:
                days = int(context.args[0])
                if days < 1:
                    raise UsageError("Days argument must be >= 1.")
                days = min(days, MAX_TIMESPAN_DAYS)
            if context.args is not None and len(context.args) > 1:
                raise UsageError()
        except (IndexError, ValueError):
            raise UsageError()

        min_timestamp = time.time_ns() - days * NS_IN_ONE_DAY
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

        ranking_msg = send_reply(
            update, context, text, save_to_db=True, is_ranking=True
        )

        if get_settings().display_remove_ranking_button:
            delete_button = InlineKeyboardButton(
                "delete ranking", callback_data=f"{ranking_msg.msg_id}__delete"
            )
            context.bot.edit_message_reply_markup(
                chat_id=ranking_msg.chat_id,
                message_id=ranking_msg.msg_id,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[delete_button]]),
            )


class TopCommandHandler(CommandHandler):
    description = "Show the most reacted messages."
    usage = "/top [days] [number of messages] [@author]"

    @staticmethod
    def _handler(update: Update, context: CallbackContext) -> None:
        assert update.message is not None
        assert context.args is not None

        days = DEFAULT_RANKING_DAYS
        requested_messages_cnt = DEFAULT_MOST_REACTED_MSGS_TO_SHOW
        try:
            if context.args:
                days = int(context.args[0])
                if days < 1 or days > MAX_TIMESPAN_DAYS:
                    raise UsageError(
                        f"Number of days must be between 1 and {MAX_TIMESPAN_DAYS}."
                    )
            if len(context.args) > 1:
                requested_messages_cnt = int(context.args[1])
                if (
                    requested_messages_cnt < 1
                    or requested_messages_cnt > MAX_TOP_MESSAGES_COUNT
                ):
                    raise UsageError(
                        f"Number of messages must be between 1 and {MAX_TOP_MESSAGES_COUNT}."
                    )
            if len(context.args) > 3:
                raise UsageError()
        except ValueError:
            raise UsageError()

        chat_id = MsgWrapper(update.message).chat_id
        min_timestamp = time.time_ns() - days * NS_IN_ONE_DAY

        query_parts = [
            "select message.original_id, count(*) as c from message "
            "inner join reaction "
            "on message.id = reaction.parent "
            "where reaction.timestamp > ? "
            "and message.chat_id = ? ",
            "group by message.id order by c desc ",
            "limit ?",
        ]
        query_arguments: list[int | str] = [
            min_timestamp,
            chat_id,
            requested_messages_cnt * 3,  # fetch more messages, as some might be deleted
        ]

        if len(context.args) > 2:
            user = context.args[2]
            if user.startswith("@"):
                user = user[1:]
            if not user:  # TODO better check for username validity
                raise UsageError("Invalid username.")
            query_parts.insert(1, "and message.author = ?")
            query_arguments.insert(2, user)

        with get_conn() as conn:
            reactions_received = conn.execute(
                "".join(query_parts), query_arguments
            ).fetchall()

        wait_time_between_messages = WAIT_TIME_BETWEEN_MESSAGES_SECONDS
        sent_cnt = 0
        for message_id, cnt in reactions_received:
            time.sleep(wait_time_between_messages)
            try:
                send_message(
                    context.bot,
                    chat_id,
                    message_id,
                    None,
                    text=f"{sent_cnt + 1}. {cnt}",
                    save_to_db=True,
                )
                sent_cnt += 1
            except telegram.error.BadRequest as e:
                if "Replied message not found" in str(e):
                    continue
                raise

            if sent_cnt >= requested_messages_cnt:
                break


class HelpCommandHandler(CommandHandler):
    description = "Show this help message."
    usage = "/help"

    @staticmethod
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

    @staticmethod
    def get_help_for_commands() -> str:
        return "\n".join(
            f"{i}. `{command.name()}` - {command.description}\nUsage: `{command.usage}`"
            for i, command in enumerate(COMMANDS, start=1)
        )

    @classmethod
    def get_help_text(cls) -> str:
        features_txt = cls.get_help_features()
        res = f"""*Features:*
{features_txt}

*Setup:*
1. Add the bot to the conversation.
2. Give it admin permissions. You can limit its permissions to only delete messages.

*Commands:*
{cls.get_help_for_commands()}

*For further support:*
[Github Repository](https://github.com/jmolinski/telegram-pyreactions-bot/)
    """
        return _escape_markdown_v2(res)

    @classmethod
    def _handler(cls, update: Update, context: CallbackContext) -> None:
        help_text = cls.get_help_text()

        if context.args:
            raise UsageError()

        send_reply(
            update,
            context,
            help_text,
            parse_mode=telegram.ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
            save_to_db=True,
        )


COMMANDS: list[Type[CommandHandler]] = CommandHandler.__subclasses__()
