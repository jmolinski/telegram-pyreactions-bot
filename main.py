from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    filters,
    MessageHandler,
    Application,
)

from src.handlers.messages_and_reactions import (
    handler_receive_message,
    handler_save_msg_to_db,
    handler_button_callback,
)
from src.handlers.commands import COMMANDS
from src.settings import configure_settings, get_settings
from src import constants


async def post_init_set_bot_commands(application: Application) -> None:
    await application.bot.set_my_commands(
        [(command.name(), command.description) for command in COMMANDS]
    )


def main() -> None:
    configure_settings(constants.CONFIG_FILENAME)
    settings = get_settings()

    application = (
        Application.builder()
        .token(settings.token)
        .post_init(post_init_set_bot_commands)
        .build()
    )

    # -- reactions & messages handlers --
    for filter_, handler in [
        (filters.TEXT & ~filters.COMMAND, handler_receive_message),
        (filters.PHOTO, handler_save_msg_to_db),
        # (filters.Sticker, handler_save_msg_to_db), TODO port to v20
    ]:
        application.add_handler(MessageHandler(filter_, handler))

    application.add_handler(
        CallbackQueryHandler(handler_button_callback, pattern="^.*$")
    )

    # -- commands handlers --
    for command in COMMANDS:
        application.add_handler(CommandHandler(command.name(), command.handler))

    application.run_polling()


if __name__ == "__main__":
    main()
