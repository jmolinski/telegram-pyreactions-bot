from typing import Optional
import json
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Updater,
    MessageHandler,
    Filters,
    CallbackContext,
    CallbackQueryHandler,
)
from db import get_conn
from collections import defaultdict
import demoji
import time
from settings import get_settings
from logger import get_logger

SETTINGS = get_settings(".env")
logger = get_logger(SETTINGS)

EMPTY_MSG = "\xad\xad"
INFORMATION_EMOJI = "ℹ️"
TEXTUAL_NORMALIZATION = {"xd": "xD", "rigcz": "RiGCz"}
TEXTUAL_REACTIONS = ("+1", "-1", "xD", "rel", "RiGCz", "rak")


def unique_list(l):
    n = []
    for item in l:
        if item not in n:
            n.append(item)
    return n


def split_into_chunks(l, n):
    return [l[i : i + n] for i in range(0, len(l), n)]


def get_markup(items):
    return InlineKeyboardMarkup(
        inline_keyboard=split_into_chunks(items, 4),
    )


def get_name_from_author_obj(data):
    username = data["username"]
    first_name = data["first_name"]
    return username or first_name


def find_emojis_in_str(s: str):
    return demoji.findall_list(s, False)


class MsgWrapper:
    def __init__(self, msg):
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


def send_message(bot, chat_id: int, parent_id: int, markup) -> MsgWrapper:
    return MsgWrapper(
        bot.send_message(
            chat_id=chat_id,
            text=EMPTY_MSG,
            reply_markup=markup,
            reply_to_message_id=parent_id,
            parse_mode="HTML",
        )
    )


def save_message_to_db(msg: MsgWrapper, is_bot_reaction=False):
    logger.info("Savin message to db")
    sql = (
        "INSERT INTO message (id, chat_id, is_reply, parent, is_bot_reaction) \n"
        f"VALUES (?, ?, ?, ?, ?);"
    )
    with get_conn() as conn:
        conn.execute(
            sql, (msg.msg_id, msg.chat_id, msg.is_reply, msg.parent, is_bot_reaction)
        )


def get_show_reaction_stats_button(parent_id):
    with get_conn() as conn:
        reactions_post_id_opt = list(
            conn.execute(
                "SELECT id from message where is_bot_reaction and parent=?",
                (parent_id,),
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


def get_updated_reactions(parent_id):
    with get_conn() as conn:
        ret = conn.execute(
            "select type, cnt, (select min(timestamp) from reaction where type=subq.type and parent=?) as time from (SELECT type, count(*) as cnt from reaction where parent=? group by type) as subq order by -cnt, time;",
            (parent_id, parent_id),
        )
        reactions = list(ret.fetchall())

    markup = [
        InlineKeyboardButton(
            f"{r[1]} {r[0]}️" if r[1] > 1 else r[0], callback_data=r[0]
        )
        for r in reactions
    ]

    if SETTINGS.show_summary_button:
        markup.append(get_show_reaction_stats_button(parent_id))

    return get_markup(markup)


def update_message_markup(bot, chat_id, message_id, parent_id):
    bot.edit_message_reply_markup(
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=get_updated_reactions(parent_id),
    )


def get_text_for_expanded(parent):
    with get_conn() as conn:
        ret = conn.execute(
            "select type, (select min(timestamp) from reaction where type=subq.type and parent=?) as time from (SELECT type, count(*) as cnt from reaction where parent=? group by type) as subq order by -cnt, time;",
            (parent, parent),
        )
        ordered_reactions = [r[0] for r in ret.fetchall()]

    with get_conn() as conn:
        ret = conn.execute(
            "SELECT type, author from reaction where parent=?;",
            (parent,),
        )
        reactions = defaultdict(list)
        for r in ret.fetchall():
            reactions[r[0]].append(r[1])

    return "\n".join(
        reaction + ": " + ", ".join(reactions[reaction])
        for reaction in ordered_reactions
    )


def add_delete_or_update_reaction_msg(bot, parent_id) -> None:
    with get_conn() as conn:
        ret = conn.execute("SELECT chat_id from message where id=?;", (parent_id,))
        chat_id = ret.fetchone()[0]

    with get_conn() as conn:
        opt_reactions_msg_id = list(
            conn.execute(
                "SELECT id, expanded from message where is_bot_reaction and parent=?",
                (parent_id,),
            ).fetchall()
        )

    reactions_markups = get_updated_reactions(parent_id)

    NO_REACTIONS = 1 if SETTINGS.show_summary_button else 0
    if len(reactions_markups.inline_keyboard[0]) == NO_REACTIONS:
        # removed last reaction
        with get_conn() as conn:
            conn.execute(
                "DELETE from message where is_bot_reaction and parent=?",
                (parent_id,),
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
                text=get_text_for_expanded(parent_id),
                parse_mode="HTML",
            )

        update_message_markup(bot, chat_id, opt_reactions_msg_id[0][0], parent_id)


def add_single_reaction(parent, author, author_id, text, timestamp):
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


def toggle_reaction(bot, parent, author, reactions, author_id):
    for r in reactions:
        add_single_reaction(parent, author, author_id, r, time.time_ns())

    add_delete_or_update_reaction_msg(bot, parent)


def receive_message(update: Update, context: CallbackContext) -> None:
    logger.info("Message received")
    if update.edited_message:
        # skip edits
        return

    msg = MsgWrapper(update["message"])

    if not msg.is_reply or not (msg.is_reaction or msg.is_many_reactions):
        save_message_to_db(msg)
    else:
        parent = msg.parent

        # odpowiedz na wiadomosc bota ma aktualizowac parenta
        with get_conn() as conn:
            opt_parent = list(
                conn.execute(
                    "SELECT parent from message where is_bot_reaction and id=?",
                    (msg.parent,),
                ).fetchall()
            )
            if opt_parent:
                parent = opt_parent[0][0]

        toggle_reaction(
            context.bot,
            parent,
            msg.author,
            msg.get_reactions_set,
            msg.author_id,
        )

        context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.msg_id)


def echo_photo(update: Update, context: CallbackContext) -> None:
    logger.info("Picture or sticker received")
    save_message_to_db(MsgWrapper(update["message"]))


def show_hide_summary(bot, cmd, parent, reaction_post_id):
    with get_conn() as conn:
        chat_id = conn.execute(
            "SELECT chat_id from message where id=?;", (parent,)
        ).fetchone()[0]

    with get_conn() as conn:
        is_expanded = conn.execute(
            "select expanded from message where id=?;", (reaction_post_id,)
        ).fetchone()[0]

        if (cmd == "show_reactions" and is_expanded) or (
            cmd == "hide_reactions" and not is_expanded
        ):
            # cant show/hide already shown/hidden
            # race condition may produce multiple show/hide commands in a row
            return

    if cmd == "show_reactions":
        new_text = get_text_for_expanded(parent)

        with get_conn() as conn:
            conn.execute(
                "UPDATE message SET expanded=TRUE where id=?;", (reaction_post_id,)
            )
    else:
        with get_conn() as conn:
            conn.execute(
                "UPDATE message SET expanded=FALSE where id=?;", (reaction_post_id,)
            )
        new_text = EMPTY_MSG

    bot.edit_message_text(
        chat_id=chat_id, message_id=reaction_post_id, text=new_text, parse_mode="HTML"
    )
    update_message_markup(bot, chat_id, reaction_post_id, parent)


def button_callback_handler(update: Update, context: CallbackContext) -> None:
    callback_data = update["callback_query"]["data"]
    parent_msg = MsgWrapper(update["callback_query"]["message"])
    author = get_name_from_author_obj(update["callback_query"]["from_user"])
    author_id = update["callback_query"]["from_user"]["id"]

    logger.info(f"button: {callback_data}, {author}\nUpdate: {update}")

    if callback_data.endswith("reactions"):
        show_hide_summary(
            context.bot, callback_data, parent_msg.parent, parent_msg.msg_id
        )
    else:
        toggle_reaction(
            context.bot,
            parent=parent_msg.parent,
            author=author,
            reactions=[callback_data],
            author_id=author_id,
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
