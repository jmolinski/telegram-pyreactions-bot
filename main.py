from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    Filters,
    MessageHandler,
    Updater,
)

from src.handlers.messages_and_reactions import (
    handler_receive_message,
    handler_save_msg_to_db,
    handler_button_callback,
)
from src.handlers.commands import (
    handler_show_ranking,
    handler_show_messages_with_most_reactions,
    handler_help,
)
from src.settings import configure_settings, get_settings
from src import constants


def main() -> None:
    configure_settings(constants.CONFIG_FILENAME)
    settings = get_settings()

    updater = Updater(settings.token, workers=1)
    dispatcher = updater.dispatcher

    # -- reactions & messages handlers --
    for filter, handler in [
        (Filters.text & ~Filters.command, handler_receive_message),
        (Filters.photo, handler_save_msg_to_db),
        (Filters.sticker, handler_save_msg_to_db),
    ]:
        dispatcher.add_handler(MessageHandler(filter, handler))

    dispatcher.add_handler(
        CallbackQueryHandler(handler_button_callback, pattern="^.*$")
    )

    # -- commands handlers --
    for command, handler, run_async in (
        ("ranking", handler_show_ranking, True),
        ("most_reacted", handler_show_messages_with_most_reactions, True),
        ("help", handler_help, True),
    ):
        dispatcher.add_handler(CommandHandler(command, handler, run_async=run_async))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
