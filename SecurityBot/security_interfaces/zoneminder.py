from collections import defaultdict

import string
import requests


class ZoneMinderInterface(object):
    name = "zoneminder"

    def __init__(self, config, permissions, logger):
        self.config = config
        self.permissions = defaultdict(list)
        self.logger = logger

        for permission in permissions:
            interface, common_id, command, option = permission.split(':')

            if interface != self.name:
                continue

            self.permissions[common_id].append((command, option))

        self.commands = {
            "arm": (self.arm_location, 1, "Arms a location, eg 'arm apartment'"),
            "disarm": (self.disarm_location, 1, "Disarms a location, eg 'disarm whitehouse'"),
            "permissions": (self.list_permissions, 0, "Shows all the loaded permissions for ZoneMinder")
        }

        self.session = None

    def get_commands(self):
        return self.commands

    def connect_to_zm(self):
        url_join_char = '/'

        if self.config["url"].endswith("/"):
            url_join_char = ''

        auth_url = "{0}{1}index.php".format(self.config["url"], url_join_char)
        auth_payload = {
            "username": self.config["username"],
            "password": self.config["password"],
            "action": "login",
            "view": "console",
        }

        self.session = requests.Session()
        auth_response = self.session.post(auth_url, data=auth_payload)

        if auth_response.status_code != requests.codes.ok:
            self.logger.error("Received a bad status code from ZoneMinder while authenticating")
            return False

        # Test out our authentication against an endpoint
        monitors_url = "{0}{1}api/monitors.json".format(self.config["url"], url_join_char)
        monitors_response = self.session.get(monitors_url)

        if monitors_response.status_code != requests.codes.ok:
            self.logger.error("Failed to log into Zoneminder correctly")
            return False

        return True

    def is_ready(self):
        if not self.connect_to_zm():
            return False

        return True

    def arm_location(self, options, common_id):
        if len(options) != 1:
            return "Uhh oh, looks like you've provided the wrong number of options to 'arm'"

        location = options[0]

        permissions = self.permissions.get(common_id)

        if not permissions:
            return "Sorry, you don't have any permissions to run that!"

        locations = [location for command, location in permissions if command in ['arm', '*']]

        if not locations:
            return "Sorry, you're not allowed to run that command!"

        if '*' not in locations and location not in locations:
            return "Sorry, you're not allowed to run this command with that location!"

        # User is allowed to run that (command, location) pair
        return "{0} has been armed!".format(string.capwords(location))

    def disarm_location(self, options, common_id):
        if len(options) != 1:
            return "Uhh oh, looks like you've provided the wrong number of options to 'disarm'"

        location = options[0]

        permissions = self.permissions.get(common_id)

        if not permissions:
            return "Sorry, you don't have any permissions to run that!"

        locations = [location for command, location in permissions if command in ['arm', '*']]

        if not locations:
            return "Sorry, you're not allowed to run that command!"

        if '*' not in locations and location not in locations:
            return "Sorry, you're not allowed to run this command with that location!"

        # User is allowed to run that (command, option) pair
        return "{0} has been disarmed!".format(string.capwords(location))

    def list_permissions(self, *_):
        pretty_list = "These are the permissions I've loaded:\n```"
        pretty_list += "{0:<15}{1:<10}{2:<10}\n".format("User", "Command", "Option")
        for common_id, permissions in self.permissions.items():
            for command, option in permissions:
                pretty_list += "{0:<15}{1:<10}{2:<10}\n".format(common_id, command, option)

        pretty_list += "```"
        return pretty_list
