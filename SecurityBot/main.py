#!/usr/bin/env python3

import os
import sys
import yaml
import argparse
import logging

import inspect
from pydoc import locate

from SecurityBot import human_interfaces
from SecurityBot import security_interfaces


class BreakListenException(Exception):
    pass


def interface_loader(module_directory):
    """
    Takes a directory that contains interface modules, we will then load every available module and return them
    :param module_directory: 
    :return: 
    """
    interfaces = {}

    module_directory_name = os.path.split(module_directory)[-1]

    for interface_file in os.listdir(module_directory):
        # Strip out __init__.py, __pycache__, etc
        if interface_file.startswith("__"):
            continue

        module_name = interface_file.split(".")[0]
        interface_module = locate(".".join(["SecurityBot", module_directory_name, module_name]))

        for _, klass in inspect.getmembers(interface_module, inspect.isclass):
            if str(klass.__name__).endswith("Interface"):
                if getattr(klass, "name") is None:
                    continue

                interfaces[klass.name] = klass
            else:
                continue

    return interfaces


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("-v", action="count", default=0, help="Determines logging verbosity")
    parser.add_argument("--config", required=True, help="Path to the SecurityBot config file")

    args = parser.parse_args()

    logger = logging.getLogger("SecurityBot")
    handler = logging.StreamHandler(sys.stdout)

    if args.v > 0:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logger.setLevel(log_level)
    handler.setLevel(log_level)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    if not os.path.exists(args.config):
        parser.error("Provided config file doesn't exist")

    with open(args.config, 'rt') as config_file:
        config = yaml.load(config_file)
        logger.debug("Loaded Config: {0}".format(config))

    # Load the interface classes
    security_interfaces = interface_loader(os.path.dirname(security_interfaces.__file__))
    logger.debug("Loaded Security Interfaces: {0}".format(", ".join(security_interfaces.keys())))

    human_interfaces = interface_loader(os.path.dirname(human_interfaces.__file__))
    logger.debug("Loaded Human Interfaces: {0}".format(", ".join(human_interfaces.keys())))

    # Choose the one specific to this config
    SecurityInterfaceClass = security_interfaces.get(config["security_interface"]["name"])
    HumanInterfaceClass = human_interfaces.get(config["human_interface"]["name"])

    # Initialize the classes
    security_interface = SecurityInterfaceClass(config["security_interface"],
                                                config["permissions"],
                                                config["locations"],
                                                logger)
    human_interface = HumanInterfaceClass(config["human_interface"], config["users"], security_interface, logger)

    # Ensure the two interfaces are ready (connect to their backend/etc)
    if not human_interface.is_ready():
        logger.error("{0} interface failed to ready up".format(human_interface.name.title()))
        sys.exit(1)

    if not security_interface.is_ready():
        logger.error("{0} interface failed to ready up".format(security_interface.name.title()))
        sys.exit(1)

    # Listen loop
    try:
        human_interface.listen_for_events()
    except BreakListenException as e:
        logger.info(e)
