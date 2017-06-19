from collections import defaultdict
from datetime import datetime, timedelta
from queue import Empty

import itertools
import requests
import time
import re


class ZoneMinderInterface(object):
    name = "zoneminder"

    ALARM_INACTIVE = 0
    ALARM_ACTIVE = 2

    def __init__(self, config, permissions, locations, queues, logger):
        self.config = config
        self.permissions = defaultdict(list)
        self.locations = dict()
        self.monitors = dict()
        self.read_queue, self.write_queue = queues
        self.logger = logger

        self.alarms = {}

        # Ensure a consistent URL format
        while self.config["url"].endswith("/"):
            self.config["url"] = self.config["url"][0:-1]

        # Check each delta setting and parse it
        time_regex = re.compile(r"^([0-9]+)([hms])$")

        delta_dict = {
            's': lambda x: timedelta(seconds=x),
            'm': lambda x: timedelta(minutes=x),
            'h': lambda x: timedelta(hours=x),
        }

        delta_defaults = {
            "alarm_alert_interval": timedelta(minutes=1),
            "alarm_expires_at": timedelta(minutes=5),
        }

        for setting_name in ["alarm_alert_interval", "alarm_expires_at"]:
            use_default = False

            if self.config[setting_name]:
                match = time_regex.match(self.config[setting_name])

                if match:
                    alert_interval, alert_delta = match.group()
                    self.config[setting_name] = delta_dict[alert_delta](int(alert_interval))
                else:
                    use_default = True
                    self.logger.error("Invalid '{0}' value".format(setting_name))
            else:
                use_default = True
                self.config[setting_name] = delta_defaults[setting_name]
                self.logger.warn("'{0}' is missing from config".format(setting_name, self.config[setting_name]))

            if use_default:
                self.config[setting_name] = delta_defaults[setting_name]
                self.logger.warn("Loading default: {1}".format(setting_name, self.config[setting_name]))

        # Parse and load all the permissions
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

        # Parse and load all the locations
        for location_string in locations:
            interface, location, monitor_id = location_string.split(':')

            if interface != self.name:
                continue

            # Build up 2 dicts for easy translation between monitors and locations
            self.locations[location] = monitor_id
            self.monitors[monitor_id] = location

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
            "ack": {
                "function": self.ack_location,
                "num_args": range(1, 4),
                "help": "Ack's a location that is currently under attack",
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
            },
            "help": {
                "function": self.list_commands,
                "num_args": range(0),
                "help": "Shows the available commands"
            },
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

        try:
            return int(monitor_status_response.json()["status"])
        except ValueError:
            return None

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

    def ack_location(self, options, common_id):
        command = "ack"
        permission_failure = self.has_permissions(command, options, common_id, option_name="location")

        if permission_failure:
            return permission_failure

        location = ' '.join(options)

        if location not in self.locations:
            return "Unknown location sorry!"

        monitor_id = self.locations[location]

        return self.ack_alarm(monitor_id, location)

    def ack_alarm(self, monitor_id, location):
        if monitor_id not in self.alarms:
            return "Err, that location is not currently under attack :face_with_rolling_eyes:"

        alarm_details = self.alarms[monitor_id]

        if alarm_details["ack"]:
            return "Err, you've already ack'd this alarm :face_with_rolling_eyes:"

        alarm_details["ack"] = True

        return "Successfully ack'd alarm for {0}".format(location)

    def status_location(self, options, common_id):
        command = "status"
        permission_failure = self.has_permissions(command, options, common_id, option_name="location")

        if permission_failure:
            return permission_failure

        location = ' '.join(options)

        if location not in self.locations:
            return "Unknown location sorry!"

        monitor_id = self.locations[location]

        if monitor_id in self.alarms:
            alarm = self.alarms[monitor_id]

            if alarm["finished"]:
                verb = "no longer"
            else:
                verb = "currently"

            response = "{0} is {1} under attack!\n\nHere are the details:\n```".format(location.title(), verb)
            response += "Alarm Raised:   {0}\n".format(alarm["started"].strftime("%Y-%m-%d %H:%M:%S"))
            response += "Alarm Updated:  {0}\n".format(alarm["updated"].strftime("%Y-%m-%d %H:%M:%S"))
            response += "Alarm Finished: {0}\n".format(alarm["finished"])
            response += "Ack'd? {0}```".format("Yes" if alarm["ack"] else "No")

            return response
        else:
            return "{0} is fine!".format(location.title())

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

    def list_commands(self, *_):
        pretty_list = "These are the commands I support:\n```"
        pretty_list += "{0:<15}{1:<10}\n".format("Command", "Help")

        for command, args in self.commands.items():
            pretty_list += "{0:<15}{1:<10}\n".format(command, args["help"])

        pretty_list += "```"
        return pretty_list

    def check_monitors(self, status_filter):
        monitor_ids = []
        for location, monitor_id in self.locations.items():
            status = self.status_of_monitor(monitor_id, location)

            if status == status_filter:
                monitor_ids.append(monitor_id)

        return monitor_ids

    def expire_old_alarms(self):
        for monitor_id, alarm_details in [(i, j) for (i, j) in self.alarms.items() if j["ack"]]:
            if not alarm_details["finished"]:
                # Alarm is still considered active, ignore it
                continue

            alarm_expires_at = alarm_details["finished"] + self.config["alarm_expires_at"]

            if datetime.utcnow() > alarm_expires_at:
                del self.alarms[monitor_id]
                # TODO: Alert the user the ack'd alarm has expired

    def update_alarm(self, monitor_id):
        alarm_details = self.alarms[monitor_id]

        if alarm_details["ack"]:
            # Alarm has been ack'd, skip it
            return

        alert_at = alarm_details["updated"] + self.config["alarm_alert_interval"]

        if datetime.utcnow() > alert_at:
            self.write_queue.put({
                "text": "btw, {0} is still under attack!".format(self.monitors[monitor_id].title()),
                "options": {
                    "channel": None
                }
            })

    def finish_alarm(self, monitor_id):
        self.alarms[monitor_id]["finished"] = True

        self.write_queue.put({
            "text": "{0} is no longer under attack!".format(self.monitors[monitor_id].title()),
            "options": {
                "channel": None
            }
        })

    def new_alarm(self, monitor_id):
        self.alarms[monitor_id] = {
            "started": datetime.utcnow(),
            "updated": datetime.utcnow(),
            "finished": None,
            "ack": False,
            "event_id": None,
        }

        self.write_queue.put({
            "text": "Uhh ohh, {0} is under attack!".format(self.monitors[monitor_id]),
            "options": {
                "channel": None
            }
        })

    def monitor(self):
        self.logger.info("ZoneMinder is connected and looking for alarms")

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
                self.logger.debug("Writen to human read queue!")
            except Empty:
                pass

            self.expire_old_alarms()

            alarmed_monitors = self.check_monitors(status_filter=self.ALARM_ACTIVE)

            for monitor_id in alarmed_monitors:
                if monitor_id in self.alarms:
                    self.update_alarm(monitor_id)
                else:
                    self.new_alarm(monitor_id)

            # Finish alarms that are no longer in alarmed_monitors
            for monitor_id in set(self.alarms.keys()).difference(alarmed_monitors):
                if not self.alarms[monitor_id]["finished"]:
                    self.finish_alarm(monitor_id)

            time.sleep(1)
