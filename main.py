from typing import Optional
import logging
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logger = logging.getLogger(__name__)

EMPTY_MSG = "\xad\xad"


def split_into_chunks(l, n):
    return [l[i : i + n] for i in range(0, len(l), n)]


def get_markup(items):
    return InlineKeyboardMarkup(
        inline_keyboard=split_into_chunks(items, 4),
    )


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

        return len(self.text) == 1 or self.text in ("+1", "-1", "xD")

    @property
    def text(self) -> str:
        if self.msg["text"].lower() == "xd":
            return "xD"
        return self.msg["text"]

    @property
    def author(self) -> str:
        return self.msg["from_user"]["username"]


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
    print("saved", is_bot_reaction)
    sql = (
        "INSERT INTO message (id, chat_id, is_reply, parent, is_bot_reaction) \n"
        f"VALUES (?, ?, ?, ?, ?);"
    )
    with get_conn() as conn:
        conn.execute(
            sql, (msg.msg_id, msg.chat_id, msg.is_reply, msg.parent, is_bot_reaction)
        )


def get_updated_reactions(chat_id, parent_id):
    with get_conn() as conn:
        ret = conn.execute(
            "SELECT type, count(*) from reaction where parent=? group by type order by -count(*);",
            (parent_id,),
        )
        reactions = list(ret.fetchall())

    markup = [
        InlineKeyboardButton(
            f"{r[1]} {r[0]}️" if r[1] > 1 else r[0], callback_data=r[0]
        )
        for r in reactions
    ]

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

        print(expanded)

    show_hide = "hide" if expanded else "show"
    markup.append(InlineKeyboardButton("❓", callback_data=show_hide + "_reactions"))

    return get_markup(markup)


def update_message_markup(bot, chat_id, message_id, parent_id):
    bot.edit_message_reply_markup(
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=get_updated_reactions(chat_id, parent_id),
    )


def add_delete_or_update_reaction_msg(bot, parent_id) -> None:
    with get_conn() as conn:
        ret = conn.execute("SELECT chat_id from message where id=?;", (parent_id,))
        chat_id = ret.fetchone()[0]

    with get_conn() as conn:
        opt_reactions_msg_id = list(
            conn.execute(
                "SELECT id from message where is_bot_reaction and parent=?",
                (parent_id,),
            ).fetchall()
        )

    reactions_markups = get_updated_reactions(chat_id, parent_id)

    if len(reactions_markups.inline_keyboard[0]) == 1:
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
        update_message_markup(bot, chat_id, opt_reactions_msg_id[0][0], parent_id)


def toggle_reaction(bot, parent, author, text):
    with get_conn() as conn:
        ret = conn.execute(
            "SELECT id from reaction where parent=? and author=? and type=?;",
            (parent, author, text),
        )
        reaction_exists = list(ret.fetchall())

        if reaction_exists:
            print("deleting")
            conn.execute("DELETE from reaction where id=?;", (reaction_exists[0][0],))
        else:
            print("adding")
            sql = "INSERT INTO reaction (parent, author, type) VALUES (?, ?, ?);"
            conn.execute(sql, (parent, author, text))

        conn.commit()

    add_delete_or_update_reaction_msg(bot, parent)


def receive_message(update: Update, context: CallbackContext) -> None:
    print("msg received")
    msg = MsgWrapper(update["message"])

    if not msg.is_reply or not msg.is_reaction:
        save_message_to_db(msg)
    else:
        # TODO odpowiedz na wiadomosc bota ma aktualizowac parenta
        toggle_reaction(context.bot, msg.parent, msg.author, msg.text)

        context.bot.delete_message(chat_id=msg.chat_id, message_id=msg.msg_id)


def echo_photo(update: Update, context: CallbackContext) -> None:
    print("msg picture")
    save_message_to_db(MsgWrapper(update["message"]))


def show_hide_summary(bot, cmd, parent, reaction_post_id):
    with get_conn() as conn:
        chat_id = conn.execute(
            "SELECT chat_id from message where id=?;", (parent,)
        ).fetchone()[0]

    with get_conn() as conn:
        is_expanded = conn.execute(
            "select expanded from messages where id=?;", (reaction_post_id,)
        ).fetchone()[0]

        if (cmd == "show_reactions" and is_expanded) or (
            cmd == "hide_reactions" and not is_expanded
        ):
            # cant show/hide already shown/hidden
            # race condition may produce multiple show/hide commands in a row
            return

    if cmd == "show_reactions":
        with get_conn() as conn:
            ret = conn.execute(
                "SELECT type, author from reaction where parent=?;",
                (parent,),
            )
            reactions = defaultdict(list)
            for r in ret.fetchall():
                reactions[r[0]].append(r[1])

        s = "\n".join(
            key + ": " + ", ".join(reactioners)
            for key, reactioners in reactions.items()
        )
        with get_conn() as conn:
            conn.execute(
                "UPDATE message SET expanded=TRUE where id=?;", (reaction_post_id,)
            )

        new_text = s
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
    author = update["callback_query"]["from_user"]["username"]

    print("button:", callback_data, author)

    if callback_data.endswith("reactions"):
        show_hide_summary(
            context.bot, callback_data, parent_msg.parent, parent_msg.msg_id
        )
    else:
        toggle_reaction(
            context.bot, parent=parent_msg.parent, author=author, text=callback_data
        )


def main() -> None:
    with open(".env") as f:
        token = json.loads(f.read())["token"]

    updater = Updater(token, workers=1)

    dispatcher = updater.dispatcher
    process_update = dispatcher.process_update

    def monkey_process_update(*args, **kwargs):
        print("processing update")
        process_update(*args, **kwargs)

    dispatcher.process_update = monkey_process_update

    dispatcher.add_handler(
        MessageHandler(Filters.text & ~Filters.command, receive_message)
    )
    dispatcher.add_handler(MessageHandler(Filters.photo, echo_photo))

    dispatcher.add_handler(
        CallbackQueryHandler(button_callback_handler, pattern="^.*$")
    )

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
