
class ZoneMinderInterface(object):
    name = "zoneminder"

    def __init__(self, config):
        self.config = config
        self.interface_status = False

    def is_ready(self):
        return self.interface_status

    def arm_system(self, system):
        pass

    def disarm_system(self, system):
        pass
