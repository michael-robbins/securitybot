
class ZoneMinderInterface(object):
    name = "zoneminder"

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.interface_status = False
        self.commands = {
            "arm": (self.arm_location, "Arms a location"),
            "disarm": (self.disarm_location, "Disarms a location"),
        }

    def get_commands(self):
        return self.commands

    def is_ready(self):
        return self.interface_status

    def arm_location(self, location):
        pass

    def disarm_location(self, location):
        pass
