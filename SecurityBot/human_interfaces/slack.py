
from SecurityBot.main import BreakListenException


class SlackInterface(object):
    name = "slack"

    def __init__(self, config, security_interface):
        self.config = config
        self.security_interface = security_interface
        self.interface_status = False

    def is_ready(self):
        return self.interface_status

    def listen_for_events(self):
        if not self.is_ready:
            raise BreakListenException("SlackInterface exiting as we're not ready")

        raise BreakListenException("Nothing more to do here")
