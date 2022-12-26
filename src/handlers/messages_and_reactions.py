from __future__ import annotations

import time

from collections import defaultdict
from typing import Any

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import CallbackContext

from src import constants

from src.db import get_conn
from src.logger import get_default_logger
from src.message_wrapper import MsgWrapper
from src.settings import get_settings
from src.utils import (
    get_name_from_author_obj,
    get_reaction_representation,
    split_into_chunks,
    extract_anon_message_text,
)

from src.handlers.common import save_message_to_db, make_msg_id, send_message


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
        constants.INFORMATION_EMOJI, callback_data=show_hide + "_reactions"
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

    if get_settings().show_summary_button:
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

    NO_REACTIONS = 1 if get_settings().show_summary_button else 0
    if len(reactions_markups.inline_keyboard[0]) == NO_REACTIONS:
        # removed last reaction
        with get_conn() as conn:
            conn.execute(
                "DELETE from message where is_bot_reaction and parent=?",
                (parent_msg_id,),
            )
        remove_message_with_retries(bot, chat_id, opt_reactions_msg_id[0][0])
    elif not opt_reactions_msg_id:
        # adding new reactions msg
        new_msg = send_message(
            bot, chat_id, parent_id=parent_id, markup=reactions_markups
        )
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
    get_default_logger().info("Hangling add/remove reaction")
    with get_conn() as conn:
        ret = conn.execute(
            "SELECT id from reaction where parent=? and author_id=? and type=?;",
            (parent, author_id, text),
        )
        reaction_exists = list(ret.fetchall())

        if reaction_exists:
            get_default_logger().info("deleting")
            conn.execute("DELETE from reaction where id=?;", (reaction_exists[0][0],))
        else:
            get_default_logger().info("adding")
            sql = "INSERT INTO reaction (parent, author, type, author_id, timestamp) VALUES (?, ?, ?, ?, ?);"
            conn.execute(sql, (parent, author, text, author_id, timestamp))

        conn.commit()


def toggle_reaction(
    bot: Bot,
    parent: int,
    author: str,
    reactions: list[str],
    author_id: int,
    chat_id: int,
) -> None:
    for r in reactions:
        add_single_reaction(
            make_msg_id(parent, chat_id), author, author_id, r, time.time_ns()
        )

    add_delete_or_update_reaction_msg(bot, parent, chat_id)


def remove_message_with_retries(
    bot: Bot, chat_id: int, message_id: int, tries: int = 3
) -> None:
    assert tries > 0

    try:
        bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:  # Not sure if all exceptions should be caught here
        if tries > 1:
            time_to_wait_before_retry = 0.025
            time.sleep(time_to_wait_before_retry)
            remove_message_with_retries(bot, chat_id, message_id, tries - 1)

        raise Exception(
            f"Failed to delete message(id={message_id}, chat_id={chat_id})"
        ) from e


def repost_anon_message(context: CallbackContext, msg: MsgWrapper) -> None:
    # first remove the original message
    remove_message_with_retries(context.bot, msg.chat_id, msg.msg_id)
    # then send a message with the same content
    extracted_anon_text = extract_anon_message_text(msg.text)
    assert extracted_anon_text is not None
    anonimized_text = get_settings().anon_msg_prefix + extracted_anon_text
    new_msg = send_message(
        context.bot, msg.chat_id, parent_id=msg.parent, text=anonimized_text
    )
    save_message_to_db(new_msg, is_anon=True)


def handler_receive_message(update: Update, context: CallbackContext) -> None:
    get_default_logger().info("Message received")
    if update.edited_message:
        # skip edits
        return

    assert update.message is not None
    msg = MsgWrapper(update.message)

    if msg.is_anon_message:
        repost_anon_message(context, msg)
        return

    if msg.parent is None or not msg.is_reaction_msg:
        save_message_to_db(msg)
    else:
        parent = msg.parent
        assert parent is not None

        get_default_logger().info("Handling a reaction message")

        get_default_logger().info("removing the reaction message")
        remove_message_with_retries(context.bot, msg.chat_id, msg.msg_id)

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


def handler_save_msg_to_db(update: Update, context: CallbackContext) -> None:
    get_default_logger().info("Picture or sticker received")
    assert update.message is not None
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
        new_text = constants.EMPTY_MSG
        with get_conn() as conn:
            conn.execute(
                "UPDATE message SET expanded=FALSE where id=?;",
                (reaction_msg_id,),
            )

    bot.edit_message_text(
        chat_id=chat_id, message_id=reaction_post_id, text=new_text, parse_mode="HTML"
    )
    update_message_markup(bot, chat_id, reaction_post_id, parent)


def handler_button_callback(update: Update, context: CallbackContext) -> None:
    assert update.callback_query is not None
    callback_query = update.callback_query
    callback_data = callback_query.data
    assert isinstance(callback_data, str)
    assert callback_query.message is not None
    parent_msg = MsgWrapper(callback_query.message)
    callback_query_data: Any = update["callback_query"]
    author = get_name_from_author_obj(callback_query_data["from_user"])
    author_id = callback_query_data["from_user"]["id"]
    chat_id = parent_msg.chat_id

    get_default_logger().info(f"button: {callback_data}, {author}\nUpdate: {update}")

    if callback_data.endswith("reactions"):
        assert parent_msg.parent is not None
        show_hide_summary(
            context.bot, callback_data, parent_msg.parent, parent_msg.msg_id, chat_id
        )
    elif callback_data.endswith("__delete"):
        assert parent_msg.parent is not None
        try:
            msg_id = int(callback_data.split("__")[0])
            remove_message_with_retries(context.bot, chat_id, msg_id)
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
