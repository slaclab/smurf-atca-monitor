#!/usr/bin/env python3

import argparse
import subprocess
import os
import logging
import rogue
import pyrogue

# Import the ATCA IPMI monitor (Static or DYnamic version)
# from atcaipmi.monitor import AtcaIpmiDynamicMonitor as AtcaIpmiMonitor
from atcaipmi.monitor import AtcaIpmiStaticMonitor as AtcaIpmiMonitor

# Import the Root, which includes a device for the while ATCA crate
from atcaipmi.atca_root import AtcaCrateRoot


def get_args():
    """
    Parse and return the inputs arguments.
    """
    parser = argparse.ArgumentParser(
        description='SMuRF ATCA Monitor')

    parser.add_argument(
        '--shelfmanager', '-S',
        type=str,
        required=True,
        dest='shelfmanager',
        help='Node name of the ATCA shelfmanager')

    parser.add_argument(
        '--port', '-p',
        type=int,
        required=False,
        default=9100,
        dest='port_number',
        help='Rogue server port number (default: 9100)')

    parser.add_argument(
        '--gui', '-g',
        action='store_true',
        dest='use_gui',
        help='Start the server with a GUI')

    parser.add_argument(
        '--log-level',
        type=str,
        required=False,
        choices=['info', 'warning', 'error'],
        default='error',
        dest='log_level',
        help='Log level (default: "error")')

    return parser.parse_args()


if __name__ == "__main__":

    # Get input arguments
    args = get_args()

    shelfmanager = args.shelfmanager
    use_gui = args.use_gui
    port_number = args.port_number
    log_level = args.log_level

    # Check if shelfmanager is online
    print(f"Trying to ping the shelfmanager '{shelfmanager}'...")
    try:
        dev_null = open(os.devnull, 'w')
        subprocess.check_call(
            ["ping", "-c2", shelfmanager],
            stdout=dev_null,
            stderr=dev_null)
        print("    shelfmanager is online")
        print("")
    except subprocess.CalledProcessError:
        print("    ERROR: shelfmanager can't be reached!")
        exit()

    # Setup the logger level. Set the 'Error' level by default
    logger = logging.getLogger('pyrogue')
    if log_level == 'info':
        logger.setLevel(rogue.Logging.Info)
    elif log_level == 'warning':
        logger.setLevel(rogue.Logging.Warning)
    else:
        logger.setLevel(rogue.Logging.Error)

    # Start the ATCA IPMI monitor
    ipmi = AtcaIpmiMonitor(shelfmanager=shelfmanager)

    # Create the ATCA crate root object
    with AtcaCrateRoot(ipmi=ipmi, serverPort=port_number) as root:

        if use_gui:

            import pyrogue.pydm
            pyrogue.pydm.runPyDM(serverList=root.zmqServer.address)

            print("GUI was closed...")
        else:
            # Stop the server when Crtl+C is pressed
            pyrogue.waitCntrlC()

            print("Closing server...")

