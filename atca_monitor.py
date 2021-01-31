#!/usr/bin/env python3

import argparse
import subprocess
import os
import logging
import rogue
import pyrogue
import pyrogue.protocols.epics

# Import the ATCA IPMI monitor (Static or DYnamic version)
# from atcaipmi.monitor import AtcaIpmiDynamicMonitor as AtcaIpmiMonitor
from atcaipmi.monitor import AtcaIpmiStaticMonitor as AtcaIpmiMonitor

# Import the Root, which includes a device for the while ATCA crate
from atcaipmi.atca_root import AtcaCrateRoot

# Setup the logger level to 'Error' by default
logger = logging.getLogger('pyrogue')
logger.setLevel(rogue.Logging.Error)


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
        '--epics', '-e',
        type=str,
        required=False,
        dest='epics_prefix',
        help='Start an EPICS server using this PV name prefix '
             '(default: the shelfmanager node name)')

    parser.add_argument(
        '--port', '-p',
        type=int,
        required=False,
        defalt=9100,
        dest='port_number',
        help='Rogue server port number')

    parser.add_argument(
        '--gui', '-g',
        action='store_true',
        dest='use_gui',
        help='Start the server with a GUI')

    return parser.parse_args()


if __name__ == "__main__":

    # Get input arguments
    args = get_args()

    shelfmanager = args.shelfmanager
    epics_prefix = args.epics_prefix
    use_gui = args.use_gui
    port_number = args.port_number

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

    # Use the shelfmanager as EPICS prefix, unless a different one
    # was defined by the user
    if not epics_prefix:
        epics_prefix = shelfmanager

    # Start the ATCA IPMI monitor
    ipmi = AtcaIpmiMonitor(shelfmanager=shelfmanager)

    # Create the ATCA crate root object
    root = AtcaCrateRoot(ipmi=ipmi, serverPort=port_number)
    root.start()

    # Create the EPICS server
    print(f"Starting EPICS server using prefix \"{epics_prefix}\"")
    epics = pyrogue.protocols.epics.EpicsCaServer(base=epics_prefix, root=root)
    epics.start()

    if use_gui:
        # Create the GUI
        import pyrogue.pydm
        pyrogue.pydm.runPyDM(root=root)

        print("GUI was closed...")
    else:
        # Stop the server when Crtl+C is pressed
        pyrogue.waitCntrlC()

        print("Closing server...")

    epics.stop()
    root.stop()
