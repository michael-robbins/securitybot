from slackclient._server import SlackConnectionError, SlackLoginError
from slackclient import SlackClient

import random
import time


class SlackInterface(object):
    name = "slack"
    web_socket_sleep_delay = 1
    no_text_messages = [
        "Err... you didn't type anything?",
        "Hi, what's up?",
        "Sorry, I didn't quite catch that",
    ]

    def __init__(self, config, security_interface, logger):
        self.config = config
        self.security_interface = security_interface
        self.logger = logger
        self.slack_client = None
        self.bot_id = config.get("bot_id", None)
        self.channel_id = config.get("channel_id", None)
        self.ready = False
        self.last_ts = float(0)

        self.available_commands = self.security_interface.get_commands()
        self.available_commands_help = "Available commands are:\n```"

        for command, (func, help_text) in self.available_commands.items():
            self.available_commands_help += "{0:<15}{1}\n".format("'{0}'".format(command), help_text)

        self.available_commands_help += "```\n\n"

    def get_bot_id(self, bot_name):
        api_call = self.slack_client.api_call("users.list")

        if api_call.get("ok", False):
            for user in api_call.get("members"):
                if user.get("name") == bot_name:
                    return user.get("id")

        return None

    def get_channel_id(self, channel_name):
        api_call = self.slack_client.api_call("channels.list", exclude_archived=1)

        if api_call.get("ok", False):
            for channel in api_call["channels"]:
                if channel["name"] == channel_name:
                    return channel["id"]

        return None

    def is_ready(self):
        # Ensure we're connected to the slack feed
        try:
            self.slack_client = SlackClient(self.config["bot_user_token"])
            if not self.slack_client.rtm_connect():
                self.logger.error("Failed to connect to the Slack API (RTM Connect Failed)")
                return False
        except SlackConnectionError:
            self.logger.error("Failed to connect to the Slack API")
            return False
        except SlackLoginError:
            self.logger.error("Failed to log into the Slack API")
            return False

        # Get our bot's ID
        if not self.bot_id:
            self.bot_id = self.get_bot_id(self.config["bot_name"].lower())

            if self.bot_id is None:
                self.logger.error("Failed to obtain the ID of the bot '{0}'".format(self.config["bot_name"]))
                return False

        self.available_commands_help += "I'm expecting the commands to look like:\n" \
                                        "<@{0}> command option1 [option2]...".format(self.bot_id)

        # Get our channel's ID
        if not self.channel_id:
            self.channel_id = self.get_channel_id(self.config["channel"].lower())

            if self.channel_id is None:
                self.logger.error("Failed to obtain the ID of the channel '{0}'".format(self.config["channel"]))
                return False

        # And we're done here
        self.ready = True

        return True

    def match_event(self, event):
        # We only want text based events
        if "text" not in event:
            return False

        # We ignore other bot messages
        if "bot_id" in event or "user" in event and event["user"] == self.bot_id:
            return False

        event_channel_id = event.get("channel")

        # Skip this event if the channel doesn't match
        if event_channel_id is not None and event_channel_id != self.channel_id:
            return False

        # We want time based text messages
        if "ts" not in event:
            return False

        # Maybe we read the same event twice off the firehose?
        event_timestamp = float(event.get("ts", "0"))
        if self.last_ts > event_timestamp:
            return False

        # Match on the bot reference being in the message
        bot_mention = "<@{0}>".format(self.bot_id)

        if bot_mention in event["text"]:
            return True

        return False

    def post_message(self, message, channel):
        self.slack_client.api_call("chat.postMessage", channel=channel, text=message, as_user=True)

    def handle_event(self, event):
        # Parse the message and drop the bot user mention
        message = event["text"].strip().lower().split(' ')[1:]
        channel = event["channel"]

        command = ''
        options = list()

        if len(message) == 0:
            self.post_message(random.choice(self.no_text_messages), channel)
            return False

        elif len(message) == 1:
            self.post_message("Ohh no :sweat:, that command needs an option!", channel)
            self.post_message(self.available_commands_help, channel)
            return False

        elif len(message) > 1:
            command = message[0]
            options = message[1:]

        if command not in self.available_commands:
            self.post_message(":thinking_face:", channel)
            time.sleep(1)
            self.post_message("I'm sorry but I don't understand your command: '{0}'".format(command), channel)
            self.post_message(self.available_commands_help, channel)
            return False

        command_function = self.available_commands[command][0]
        self.post_message(command_function(options), channel)

    def listen_for_events(self):
        if not self.ready:
            raise RuntimeError("is_ready has not been called/returned false")

        if not self.slack_client.rtm_connect():
            raise RuntimeError("Failed to connect to the Slack API")

        self.logger.info("Slack is connected and listening for mentions")

        while True:
            for event in self.slack_client.rtm_read():
                if not event:
                    continue

                if self.match_event(event):
                    self.handle_event(event)

            time.sleep(SlackInterface.web_socket_sleep_delay)
