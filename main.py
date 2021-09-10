from __future__ import annotations

import time

from collections import defaultdict
from typing import List, Optional

from telegram import (
    Bot,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ParseMode,
    Update,
)
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    Filters,
    MessageHandler,
    Updater,
)

import constants

from constants import EMPTY_MSG, INFORMATION_EMOJI
from db import get_conn
from logger import get_logger
from message_wrapper import MsgWrapper
from settings import get_settings
from utils import (
    _escape_markdown_v2,
    get_name_from_author_obj,
    get_reaction_representation,
    split_into_chunks,
)

SETTINGS = get_settings(constants.CONFIG_FILENAME)
logger = get_logger(SETTINGS)


def make_msg_id(msg_id: int, chat_id: int) -> str:
    return f"{abs(chat_id)}:{abs(msg_id)}"


def send_message(
    bot: Bot,
    chat_id: int,
    parent_id: int,
    markup: Optional[InlineKeyboardMarkup],
    text: Optional[str] = None,
) -> MsgWrapper:
    if text is None:
        text = EMPTY_MSG

    if markup:
        return MsgWrapper(
            bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=markup,
                reply_to_message_id=parent_id,
                parse_mode="HTML",
            )
        )
    else:
        return MsgWrapper(
            bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=parent_id,
                parse_mode="HTML",
            )
        )


def save_message_to_db(
    msg: MsgWrapper, is_bot_reaction: bool = False, is_ranking: bool = False
) -> None:
    logger.info("Savin message to db")
    sql = (
        "INSERT INTO message (id, original_id, author_id, author, chat_id, parent, is_bot_reaction, is_ranking) \n"
        f"VALUES (?, ?, ?, ?, ?, ?, ?, ?);"
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
            ),
        )


def get_show_reaction_stats_button(
    chat_id: int, parent_id: int
) -> InlineKeyboardButton:
    with get_conn() as conn:
        reactions_post_id_opt = list(
            conn.execute(
                "SELECT id from message where is_bot_reaction and parent=?",
                (make_msg_id(parent_id, chat_id),),
            ).fetchall()
        )
        if reactions_post_id_opt:
            expanded = conn.execute(
                "SELECT expanded from message where id=?;",
                (reactions_post_id_opt[0][0],),
            ).fetchone()[0]
        else:
            expanded = False

    show_hide = "hide" if expanded else "show"
    return InlineKeyboardButton(
        INFORMATION_EMOJI, callback_data=show_hide + "_reactions"
    )


def get_updated_reactions(parent_id: int, chat_id: int) -> InlineKeyboardMarkup:
    msg_id = make_msg_id(parent_id, chat_id)

    with get_conn() as conn:
        ret = conn.execute(
            "select type, cnt, (select min(timestamp) from reaction where type=subq.type and parent=?) as time from (SELECT type, count(*) as cnt from reaction where parent=? group by type) as subq order by -cnt, time;",
            (msg_id, msg_id),
        )
        reactions = list(ret.fetchall())

    markup = [
        InlineKeyboardButton(
            get_reaction_representation(r[0], r[1], with_count=True), callback_data=r[0]
        )
        for r in reactions
    ]

    if SETTINGS.show_summary_button:
        markup.append(get_show_reaction_stats_button(chat_id, parent_id))

    return InlineKeyboardMarkup(
        inline_keyboard=split_into_chunks(markup, 4),
    )


def update_message_markup(
    bot: Bot, chat_id: int, message_id: int, parent_id: int
) -> None:
    bot.edit_message_reply_markup(
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=get_updated_reactions(parent_id, chat_id),
    )


def get_text_for_expanded(parent: int, chat_id: int) -> str:
    msg_id = make_msg_id(parent, chat_id)

    with get_conn() as conn:
        ret = conn.execute(
            "select type, cnt, (select min(timestamp) from reaction where type=subq.type and parent=?) as time "
            "from (SELECT type, count(*) as cnt from reaction where parent=? group by type) as subq order by -cnt, time;",
            (msg_id, msg_id),
        )
        ordered_reactions = [(r[0], r[1]) for r in ret.fetchall()]

    with get_conn() as conn:
        ret = conn.execute(
            "SELECT type, author from reaction where parent=?;",
            (msg_id,),
        )
        reactions = defaultdict(list)
        for r in ret.fetchall():
            reactions[r[0]].append(r[1])

    return "\n".join(
        get_reaction_representation(reaction, count)
        + ": "
        + ", ".join(reactions[reaction])
        for reaction, count in ordered_reactions
    )


def add_delete_or_update_reaction_msg(bot: Bot, parent_id: int, chat_id: int) -> None:
    parent_msg_id = make_msg_id(parent_id, chat_id)

    with get_conn() as conn:
        opt_reactions_msg_id = list(
            conn.execute(
                "SELECT original_id, expanded from message where is_bot_reaction and parent=?",
                (parent_msg_id,),
            ).fetchall()
        )

    reactions_markups = get_updated_reactions(parent_id, chat_id)

    NO_REACTIONS = 1 if SETTINGS.show_summary_button else 0
    if len(reactions_markups.inline_keyboard[0]) == NO_REACTIONS:
        # removed last reaction
        with get_conn() as conn:
            conn.execute(
                "DELETE from message where is_bot_reaction and parent=?",
                (parent_msg_id,),
            )
        bot.delete_message(chat_id=chat_id, message_id=opt_reactions_msg_id[0][0])
    elif not opt_reactions_msg_id:
        # adding new reactions msg
        new_msg = send_message(bot, chat_id, parent_id, reactions_markups)
        save_message_to_db(new_msg, is_bot_reaction=True)
    else:
        # updating existing reactions post
        # if expanded update text
        if opt_reactions_msg_id[0][1]:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=opt_reactions_msg_id[0][0],
                text=get_text_for_expanded(parent_id, chat_id),
                parse_mode="HTML",
            )

        update_message_markup(bot, chat_id, opt_reactions_msg_id[0][0], parent_id)


def add_single_reaction(
    parent: str, author: str, author_id: int, text: str, timestamp: int
) -> None:
    logger.info("Hangling add/remove reaction")
    with get_conn() as conn:
        ret = conn.execute(
            "SELECT id from reaction where parent=? and author_id=? and type=?;",
            (parent, author_id, text),
        )
        reaction_exists = list(ret.fetchall())

        if reaction_exists:
            logger.info("deleting")
            conn.execute("DELETE from reaction where id=?;", (reaction_exists[0][0],))
        else:
            logger.info("adding")
            sql = "INSERT INTO reaction (parent, author, type, author_id, timestamp) VALUES (?, ?, ?, ?, ?);"
            conn.execute(sql, (parent, author, text, author_id, timestamp))

        conn.commit()


def toggle_reaction(
    bot: Bot,
    parent: int,
    author: str,
    reactions: List[str],
    author_id: int,
    chat_id: int,
) -> None:
    for r in reactions:
        add_single_reaction(
            make_msg_id(parent, chat_id), author, author_id, r, time.time_ns()
        )

    add_delete_or_update_reaction_msg(bot, parent, chat_id)


def receive_message(update: Update, context: CallbackContext) -> None:
    logger.info("Message received")
    if update.edited_message:
        # skip edits
        return

    msg = MsgWrapper(update.message)

    if msg.parent is None or not msg.is_reaction_msg:
        save_message_to_db(msg)
    else:
        assert msg.parent is not None
        parent: int = msg.parent

        # odpowiedz na wiadomosc bota ma aktualizowac parenta
        with get_conn() as conn:
            opt_parent = list(
                conn.execute(
                    "SELECT parent from message where is_bot_reaction and id=?",
                    (make_msg_id(parent, msg.chat_id),),
                ).fetchall()
            )
            if opt_parent:
                parent = conn.execute(
                    "SELECT original_id from message where id=?",
                    (opt_parent[0][0],),
                ).fetchone()[0]

        toggle_reaction(
            context.bot,
            parent,
            msg.author,
            msg.get_reactions_list,
            msg.author_id,
            msg.chat_id,
        )

        context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.msg_id)


def echo_photo(update: Update, context: CallbackContext) -> None:
    logger.info("Picture or sticker received")
    save_message_to_db(MsgWrapper(update.message))


def show_hide_summary(
    bot: Bot, cmd: str, parent: int, reaction_post_id: int, chat_id: int
) -> None:
    reaction_msg_id = make_msg_id(reaction_post_id, chat_id)

    with get_conn() as conn:
        is_expanded = conn.execute(
            "select expanded from message where id=?;", (reaction_msg_id,)
        ).fetchone()[0]

        if (cmd == "show_reactions" and is_expanded) or (
            cmd == "hide_reactions" and not is_expanded
        ):
            # cant show/hide already shown/hidden
            # race condition may produce multiple show/hide commands in a row
            return

    if cmd == "show_reactions":
        new_text = get_text_for_expanded(parent, chat_id)
        with get_conn() as conn:
            conn.execute(
                "UPDATE message SET expanded=TRUE where id=?;",
                (reaction_msg_id,),
            )
    else:
        new_text = EMPTY_MSG
        with get_conn() as conn:
            conn.execute(
                "UPDATE message SET expanded=FALSE where id=?;",
                (reaction_msg_id,),
            )

    bot.edit_message_text(
        chat_id=chat_id, message_id=reaction_post_id, text=new_text, parse_mode="HTML"
    )
    update_message_markup(bot, chat_id, reaction_post_id, parent)


def button_callback_handler(update: Update, context: CallbackContext) -> None:
    callback_query: CallbackQuery = update.callback_query
    callback_data = callback_query.data
    parent_msg = MsgWrapper(callback_query.message)
    author = get_name_from_author_obj(update["callback_query"]["from_user"])
    author_id = update["callback_query"]["from_user"]["id"]
    chat_id = parent_msg.chat_id

    logger.info(f"button: {callback_data}, {author}\nUpdate: {update}")

    if callback_data.endswith("reactions"):
        assert parent_msg.parent is not None
        show_hide_summary(
            context.bot, callback_data, parent_msg.parent, parent_msg.msg_id, chat_id
        )
    elif callback_data.endswith("__delete"):
        assert parent_msg.parent is not None
        try:
            msg_id = int(callback_data.split("__")[0])
            context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except:
            pass
    else:
        assert parent_msg.parent is not None
        toggle_reaction(
            context.bot,
            parent=parent_msg.parent,
            author=author,
            reactions=[callback_data],
            author_id=author_id,
            chat_id=chat_id,
        )

    context.bot.answer_callback_query(update.callback_query.id)


def show_ranking(update: Update, context: CallbackContext) -> None:
    try:
        days = 7
        if context.args:
            days = int(context.args[0])
            if days < 1:
                update.message.reply_text("Days argument must be >= 1.")
                return
    except (IndexError, ValueError):
        update.message.reply_text("Usage: /ranking <optional days>")
        return

    min_timestamp = time.time_ns() - days * (24 * 60 * 60 * 10 ** 9)
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
    save_message_to_db(ranking_msg, is_bot_reaction=False, is_ranking=True)
    delete_button = InlineKeyboardButton(
        "delete ranking", callback_data=f"{ranking_msg.msg_id}__delete"
    )
    context.bot.edit_message_reply_markup(
        chat_id=ranking_msg.chat_id,
        message_id=ranking_msg.msg_id,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[delete_button]]),
    )


def get_help_features() -> str:
    disallowed_reactions = ", ".join(
        f"`{reaction}`" for reaction in SETTINGS.disallowed_reactions
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
            SETTINGS.custom_text_reaction_allowed,
        ),
        (
            fr"Banned reactions are: {disallowed_reactions}, `+n`, `-n` \(where `n != 1`\).",
            SETTINGS.disallowed_reactions,
        ),
        ("Reply with `+1` to upvote or `-1` to downvote.", True),
        ("Click on an already added reaction to also react with it.", True),
        (
            "If you have already reacted you can click on this reaction to remove it.",
            True,
        ),
        (
            fr"Click on the last reaction *\(*{constants.INFORMATION_EMOJI}*\)* to toggle reactions summary.",
            SETTINGS.show_summary_button,
        ),
    ]

    enabled_features = (f for f, enabled in features if enabled)
    return "\n".join(
        f"{i}. {feature}" for i, feature in enumerate(enabled_features, start=1)
    )


def _get_help_text() -> str:
    features_txt = get_help_features()
    res = f"""*Features:*
{features_txt}

*Setup:*
1. Add the bot to the conversation.
2. Give it admin permissions. You can limit its permissions to only delete messages.

*For further support:*
[Github Repository](https://github.com/jmolinski/telegram-pyreactions-bot/)
"""
    return _escape_markdown_v2(res)


def help_handler(update: Update, context: CallbackContext) -> None:
    help_text = _get_help_text()

    update.message.reply_text(
        help_text, parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True
    )


def main() -> None:
    updater = Updater(SETTINGS.token, workers=1)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(
        MessageHandler(Filters.text & ~Filters.command, receive_message)
    )
    dispatcher.add_handler(MessageHandler(Filters.photo, echo_photo))
    dispatcher.add_handler(MessageHandler(Filters.sticker, echo_photo))
    dispatcher.add_handler(
        CallbackQueryHandler(button_callback_handler, pattern="^.*$")
    )

    dispatcher.add_handler(CommandHandler("ranking", show_ranking, run_async=False))
    dispatcher.add_handler(CommandHandler("help", help_handler, run_async=True))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
