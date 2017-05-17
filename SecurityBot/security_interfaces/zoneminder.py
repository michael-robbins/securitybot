
class ZoneMinderInterface(object):
    name = "zoneminder"

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

        self.commands = {
            "arm": (self.arm_location, "Arms a location"),
            "disarm": (self.disarm_location, "Disarms a location"),
        }

    def get_commands(self):
        return self.commands

    def is_ready(self):
        return True

    def arm_location(self, location):
        location = location[0]
        return "{0} has been armed!".format(location.title())

    def disarm_location(self, location):
        location = location[0]
        return "{0} has been disarmed!".format(location.title())
