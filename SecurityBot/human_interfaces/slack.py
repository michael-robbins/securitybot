from slackclient._server import SlackConnectionError, SlackLoginError
from slackclient import SlackClient

import time


class SlackInterface(object):
    name = "slack"
    web_socket_sleep_delay = 1

    def __init__(self, config, security_interface, logger):
        self.config = config
        self.security_interface = security_interface
        self.logger = logger
        self.slack_client = None
        self.bot_id = config.get("bot_id", None)
        self.bot_reference = None
        self.ready = False

        self.available_commands = self.security_interface.get_commands()
        self.available_commands_help = "Available commands are:\n"

        for command, (func, help_text) in self.available_commands:
            self.available_commands_help += "* {0}: {1}\n".format(command, help_text)

    def get_bot_id(self, bot_name):
        api_call = self.slack_client.api_call("users.list")

        if api_call.get("ok"):
            users = api_call.get('members')
            for user in users:
                if user.get("name") == bot_name:
                    return user.get("id")
        else:
            return None

    def is_ready(self):
        try:
            self.slack_client = SlackClient(self.config["bot_user_token"])
        except SlackConnectionError:
            self.logger.error("Failed to connect to the Slack API")
            return False
        except SlackLoginError:
            self.logger.error("Failed to log into the Slack API")
            return False

        if self.bot_id is None or self.bot_id == '':
            self.bot_id = self.get_bot_id(self.config["bot_name"])

            if self.bot_id is None:
                self.logger.error("Failed to obtain the ID of the bot '{0}'".format(self.config["bot_name"]))
                return False

        self.bot_reference = "<@{0}>".format(self.bot_id)
        self.ready = True

        return True

    @staticmethod
    def match_event(event, bot_reference, channel=None):
        if not event:
            return None, None

        # We only want text based events
        if "text" not in event:
            return None, None

        event_channel = event.get("channel")

        # Skip this event if the channel doesn't match
        if channel is not None:
            if event_channel is not None and event_channel != channel:
                return None, None

        # Match on the bot reference being in the message
        if bot_reference in event["text"]:
            print("Found '{0}' in '{1}'".format(bot_reference, event["text"]))
            event_text = event["text"].split(bot_reference)[1].strip().lower()

            return event_text, event_channel

        return None, None

    def post_message(self, message, channel):
        self.slack_client.api_call("chat.postMessage", channel=channel, text=message, as_user=True)

    def handle_message(self, message, channel):
        message = message.split(' ')

        if len(message) < 2:
            self.post_message("I'm sorry but your command doesn't look valid.", channel)
            self.post_message("I'm expecting commands to be structured like: @myself command option", channel)

        command = message[0]
        if command not in self.available_commands:
            self.post_message("I'm sorry but I don't understand your command: '{0}'".format(command))
            self.post_message(self.available_commands_help, channel)

        command_function = self.available_commands[command][1][0]

        self.post_message(command_function(message[1:]), channel)

    def listen_for_events(self):
        if not self.ready:
            raise RuntimeError("is_ready has not been called/returned false")

        if not self.slack_client.rtm_connect():
            raise RuntimeError("Failed to connect to the Slack API")

        while True:
            for event in self.slack_client.rtm_read():
                event_text, channel = self.match_event(event, self.bot_reference, self.config["channel"])

                if event_text and channel:
                    self.handle_message(event_text, channel)

            time.sleep(SlackInterface.web_socket_sleep_delay)
