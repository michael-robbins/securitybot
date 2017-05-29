from collections import defaultdict
from queue import Empty

import itertools
import requests
import time


class ZoneMinderInterface(object):
    name = "zoneminder"

    def __init__(self, config, permissions, locations, queues, logger):
        self.config = config
        self.permissions = defaultdict(list)
        self.locations = dict()
        self.read_queue, self.write_queue = queues
        self.logger = logger

        # Ensure a consistent URL format
        while self.config["url"].endswith("/"):
            self.config["url"] = self.config["url"][0:-1]

        for permission in permissions:
            interface, common_id, command, option = permission.split(':')

            if interface != self.name:
                continue

            if ',' in command:
                commands = command.split(',')
            else:
                commands = [command]

            if ',' in option:
                options = option.split(',')
            else:
                options = [option]

            for command in commands:
                for option in options:
                    self.permissions[common_id].append((command, option))

        for location_string in locations:
            interface, location, monitor_id = location_string.split(':')

            if interface != self.name:
                continue

            self.locations[location] = monitor_id

        self.commands = {
            "arm": {
                "function": self.arm_location,
                "num_args": range(1, 4),
                "help": "Arms a location, eg 'arm apartment'",
            },
            "disarm": {
                "function": self.disarm_location,
                "num_args": range(1, 4),
                "help": "Disarms a location, eg 'disarm apartment'",
            },
            "status": {
                "function": self.status_location,
                "num_args": range(1, 4),
                "help": "Shows the status of the location, eg 'status apartment'"
            },
            "permissions": {
                "function": self.list_permissions,
                "num_args": range(0),
                "help": "Shows all the loaded permissions for ZoneMinder",
            },
            "locations": {
                "function": self.list_locations,
                "num_args": range(0),
                "help": "Shows all the loaded locations for ZoneMinder",
            }
        }

        self.session = None

    def get_commands(self):
        return self.commands

    def connect_to_zm(self):
        auth_url = "{0}/index.php".format(self.config["url"])
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
        monitors_url = "{0}/api/monitors.json".format(self.config["url"])
        monitors_response = self.session.get(monitors_url)

        if monitors_response.status_code != requests.codes.ok:
            self.logger.error("Failed to log into Zoneminder correctly")
            return False

        return True

    def status_of_monitor(self, monitor_id, location):
        endpoint = "{0}/api/monitors/alarm/id:{1}/command:status.json".format(self.config["url"], monitor_id)

        monitor_status_response = self.session.get(endpoint)

        if monitor_status_response.status_code != requests.codes.ok:
            return "Failed to get the status of {0}, sorry :sob:".format(location.title())

        status = int(monitor_status_response.json()["status"])

        if status == 0:
            return "{0} is fine!".format(location.title())
        elif status == 2:
            return "{0} totes under attack!".format(location.title())
        else:
            return "{0} is returning an unknown status of {1}!".format(location.title(), status)

    def arm_monitor(self, monitor_id, location):
        mode = "Modect"
        endpoint = "{0}/api/monitors/{1}.json".format(self.config["url"], monitor_id)
        payload = {
            "Monitor[Function]": mode,
            "Monitor[Enabled]": 1,
        }

        arm_response = self.session.post(endpoint, data=payload)

        if arm_response.status_code != requests.codes.ok:
            return "Failed to arm {0}, sorry :sob:".format(location.title())

        return "Armed!"

    def disarm_monitor(self, monitor_id, location):
        mode = "Monitor"
        endpoint = "{0}/api/monitors/{1}.json".format(self.config["url"], monitor_id)
        payload = {
            "Monitor[Function]": mode,
            "Monitor[Enabled]": 1,
        }

        disarm_response = self.session.post(endpoint, data=payload)

        if disarm_response.status_code != requests.codes.ok:
            return "Failed to disarm {0}, sorry :sob:".format(location.title())

        return "Disarmed!"

    def is_ready(self):
        if not self.connect_to_zm():
            return False

        return True

    def has_permissions(self, command, options, common_id, option_name="option"):
        if command not in self.commands.keys():
            self.logger.error("The permission check got an unknown command")
            return False

        permissions = self.permissions.get(common_id)

        if not permissions:
            return "Sorry, you don't have any permissions to run that!"

        if len(options) not in self.commands[command]["num_args"]:
            return "Uhh oh, looks like you've provided the wrong number of options to '{0}'".format(command)

        allowed_options = [o.split(' ') for c, o in permissions if c in [command, '*']]

        if not allowed_options:
            return "Sorry, you're not allowed to run that command!"

        flat_allowed_options = list(itertools.chain.from_iterable(allowed_options))

        if '*' not in allowed_options:
            for option in options:
                if option not in flat_allowed_options:
                    return "Sorry, you're not allowed to run this command with that {0}!".format(option_name)

        return None

    def arm_location(self, options, common_id):
        command = "arm"
        permission_failure = self.has_permissions(command, options, common_id, option_name="location")

        if permission_failure:
            return permission_failure

        location = ' '.join(options)

        if location not in self.locations:
            return "Unknown location sorry!"

        monitor_id = self.locations[location]

        return self.arm_monitor(monitor_id, location)

    def disarm_location(self, options, common_id):
        command = "disarm"
        permission_failure = self.has_permissions(command, options, common_id, option_name="location")

        if permission_failure:
            return permission_failure

        location = ' '.join(options)

        if location not in self.locations:
            return "Unknown location sorry!"

        monitor_id = self.locations[location]

        return self.disarm_monitor(monitor_id, location)

    def status_location(self, options, common_id):
        command = "status"
        permission_failure = self.has_permissions(command, options, common_id, option_name="location")

        if permission_failure:
            return permission_failure

        location = ' '.join(options)

        if location not in self.locations:
            return "Unknown location sorry!"

        monitor_id = self.locations[location]

        return self.status_of_monitor(monitor_id, location)

    def list_permissions(self, *_):
        pretty_list = "These are the permissions I've loaded:\n```"
        pretty_list += "{0:<15}{1:<10}{2:<10}\n".format("User", "Command", "Option")
        for common_id, permissions in self.permissions.items():
            for command, option in permissions:
                pretty_list += "{0:<15}{1:<10}{2:<10}\n".format(common_id, command, option)

        pretty_list += "```"
        return pretty_list

    def list_locations(self, *_):
        pretty_list = "These are the locations I've loaded:\n```"
        pretty_list += "{0:<20}{1:<10}\n".format("Location", "Monitor ID")
        for location, monitor_id in self.locations.items():
            pretty_list += "{0:<20}{1:<10}\n".format(location, monitor_id)

        pretty_list += "```"
        return pretty_list

    def watch_for_events(self):
        while True:
            # Check ZoneMinder for any new alerts
            # Parse the alert and extract a picture/frame
            # Send the picture/alert/message into the write queue
            try:
                message = self.read_queue.get(block=False)
                self.logger.debug(message)
                command = self.commands[message["command"]]["function"]
                response = command(message["options"], message["common_id"])

                self.write_queue.put({
                    "text": response,
                    "options": message["response_options"],
                })
            except Empty:
                pass

            time.sleep(1)
