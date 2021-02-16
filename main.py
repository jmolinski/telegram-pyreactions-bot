from __future__ import annotations

import time

from collections import defaultdict
from typing import List

from telegram import (
    Bot,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    Filters,
    MessageHandler,
    Updater,
)

from constants import EMPTY_MSG, INFORMATION_EMOJI
from db import get_conn
from logger import get_logger
from message_wrapper import MsgWrapper
from settings import get_settings
from utils import (
    get_name_from_author_obj,
    get_reaction_representation,
    split_into_chunks,
)

SETTINGS = get_settings(".env")
logger = get_logger(SETTINGS)


def make_msg_id(msg_id: int, chat_id: int) -> str:
    return f"{abs(chat_id)}:{abs(msg_id)}"


def send_message(
    bot: Bot, chat_id: int, parent_id: int, markup: InlineKeyboardMarkup
) -> MsgWrapper:
    return MsgWrapper(
        bot.send_message(
            chat_id=chat_id,
            text=EMPTY_MSG,
            reply_markup=markup,
            reply_to_message_id=parent_id,
            parse_mode="HTML",
        )
    )


def save_message_to_db(msg: MsgWrapper, is_bot_reaction: bool = False) -> None:
    logger.info("Savin message to db")
    sql = (
        "INSERT INTO message (id, original_id, chat_id, parent, is_bot_reaction) \n"
        f"VALUES (?, ?, ?, ?, ?);"
    )
    with get_conn() as conn:
        conn.execute(
            sql,
            (
                make_msg_id(msg.msg_id, msg.chat_id),
                msg.msg_id,
                msg.chat_id,
                None if msg.parent is None else make_msg_id(msg.parent, msg.chat_id),
                is_bot_reaction,
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
            "select type, cnt, (select min(timestamp) from reaction where type=subq.type and parent=?) as time from (SELECT type, count(*) as cnt from reaction where parent=? group by type) as subq order by -cnt, time;",
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

    if msg.parent is None or not (msg.is_reaction or msg.is_many_reactions):
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

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
