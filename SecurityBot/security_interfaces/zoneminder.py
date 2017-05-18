import string


class ZoneMinderInterface(object):
    name = "zoneminder"

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger

        self.commands = {
            "arm": (self.arm_location, "Arms a location, eg 'arm micks apartment'"),
            "disarm": (self.disarm_location, "Disarms a location, eg 'disarm white house'"),
        }

    def get_commands(self):
        return self.commands

    def is_ready(self):
        return True

    def arm_location(self, options):
        location = ' '.join(options)
        return "{0} has been armed!".format(string.capwords(location))

    def disarm_location(self, options):
        location = ' '.join(options)
        return "{0} has been disarmed!".format(string.capwords(location))
