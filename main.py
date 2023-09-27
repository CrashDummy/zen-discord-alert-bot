import os
import dotenv
import lightbulb
import hikari
import dataset
import asyncio
import argparse
import logging
from easygoogletranslate import EasyGoogleTranslate
from logging import info
from yahoo import check_yahoo_auctions
from mercari import check_mercari

# Load environment variables from .env file
dotenv.load_dotenv()

# Parse command line arguments
parser = argparse.ArgumentParser(description="Discord bot for monitoring ZenMarket items.")
parser.add_argument("--db-file", default="alerts.db", help="SQLite database file location")
parser.add_argument("--debug", action="store_true", help="Enable debug mode")
args = parser.parse_args()

# Configure logging
logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)

# Initialize Google Translate translator
translator = EasyGoogleTranslate(source_language="jp", target_language="en", timeout=10)

# Use the specified database file location
db = dataset.connect(f"sqlite:///{args.db_file}")

# Read the bot token from the .env file
bot_token = os.environ.get("BOT_TOKEN")
if bot_token is None:
    raise ValueError("BOT_TOKEN is not defined in the .env file.")
else:
    # Initialize the bot with the provided token
    bot = lightbulb.BotApp(bot_token)

bot.d.table = db["alerts"]
bot.d.synced = db["synced_alerts"]


# Define a function to continuously check alerts
async def check_alerts() -> None:
    while True:
        # Retrieve all alerts from the database
        alerts = bot.d.table.all()

        for alert in alerts:
            info(f"Searching for {alert['name']}...")

            # Check Yahoo Auctions if enabled
            if os.getenv("ENABLE_YAHOO_AUCTION", "true") == "true":
                try:
                    await check_yahoo_auctions(bot, translator, alert)
                except Exception as e:
                    info(f"Error: {e}")

            # Check Mercari if enabled
            if os.getenv("ENABLE_MERCARI", "true") == "true":
                try:
                    await check_mercari(bot, alert)
                except Exception as e:
                    info(f"Error: {e}")

        # Log when alert checking is complete and sleep until the next check
        info(
            f"Done checking alerts. Sleeping for {os.getenv('CHECK_INTERVAL', 60)}s..."
        )
        await asyncio.sleep(int(os.getenv("CHECK_INTERVAL", 60)))


# Define an event listener for bot's on_ready event
@bot.listen()
async def on_ready(event: hikari.StartingEvent) -> None:
    info("Starting event loop...")
    asyncio.create_task(check_alerts())


# Define a bot command to register an alert
@bot.command
@lightbulb.option("name", "Name of the item to register.", required=True)
@lightbulb.command(
    "register", "Register a new alert for a ZenMarket item.", pass_options=True
)
@lightbulb.implements(lightbulb.SlashCommand)
async def register(ctx: lightbulb.SlashContext, name: str) -> None:
    if any(True for _ in bot.d.table.find(name=name)):
        await ctx.respond(f"Alert for **{name}** already exists!")
        return

    # Insert the new alert into the database
    bot.d.table.insert(
        {
            "user_id": ctx.author.id,
            "channel_id": ctx.channel_id,
            "name": name,
        }
    )
    await ctx.respond(f"Registered alert for **{name}**!")


# Define a bot command to unregister an alert
@bot.command
@lightbulb.option("name", "Name of the item to delete.", required=True)
@lightbulb.command("unregister", "Delete an alert", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def unregister(ctx: lightbulb.SlashContext, name: str) -> None:
    if not bot.d.table.find_one(name=name):
        await ctx.respond(f"Alert for **{name}** does not exist!")
        return

    # Delete the alert from the database
    bot.d.table.delete(user_id=ctx.author.id, name=name)
    await ctx.respond(f"Unregistered alert for **{name}**!")


# Define a bot command to list user's alerts
@bot.command
@lightbulb.command("alerts", "List alerts")
@lightbulb.implements(lightbulb.SlashCommand)
async def alerts(ctx: lightbulb.SlashContext) -> None:
    alerts = bot.d.table.find(user_id=ctx.author.id)
    if all(False for _ in alerts):
        await ctx.respond("You have no alerts!")
        return

    # Respond with a list of user's alerts
    await ctx.respond("\n".join([f"{alert['name']}" for alert in alerts]) or "None")


# Main entry point for running the bot
if __name__ == "__main__":
    try:
        bot.run(
            activity=hikari.Activity(
                name="ZenMarket items", type=hikari.ActivityType.WATCHING
            )
        )

    except KeyboardInterrupt:
        info("Bot terminated by user (Ctrl-C).")
