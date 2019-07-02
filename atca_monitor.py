#!/usr/bin/env python3

import getopt
import subprocess
import os
import time
import sys
import pyrogue
import pyrogue.gui
import pyrogue.protocols.epics

# Import the ATCA IPMI monitor (Static or DYnamic version)
#from atcaipmi.monitor import AtcaIpmiDynamicMonitor as AtcaIpmiMonitor
from atcaipmi.monitor import AtcaIpmiStaticMonitor as AtcaIpmiMonitor

# Import the Root, which includes a device for the while ATCA crate
from atcaipmi.atca_root import AtcaCrateRoot

def usage(name):
    """
    Usage message.

    Args:
        name: name of this script.

    Returns:
        None.
    """
    print("Usage: {} -S|--shelfmanager <shelfmanager> [-e|--epics prefix] [-g|--gui] [-h|--help]".format(name))
    print("")
    print("    -S|--shelfmanager <shelfmanager> : Node name of the ATCA shelfmanager.")
    print("    -e|--epics        <prefix>       : Start an EPICS server using <prefix> as the PV name prefix.")
    print("                                       (default: the shelfmanager node name)")
    print("    -g|--gui                         : Start the server with a GUI.")
    print("    -h|--help                        : Show this message")
    print("")
    print("")

if __name__ == "__main__":

    shelfmanager=""
    epics_prefix=""
    use_gui=False
    # Read Arguments
    try:
        opts, _ = getopt.getopt(sys.argv[1:],
                "S:e:gh",
                ["shelfmanager","epics","gui","help"])
    except getopt.GetoptError:
        usage(sys.argv[0])
        sys.exit()

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage(sys.argv[0])
            sys.exit()
        elif opt in ("-S", "--shelfmanager"):
            shelfmanager = arg
        elif opt in ("-g", "--gui"):
            use_gui = True
        elif opt in ("-e", "--epics"):
            epics_prefix = arg

    # Check mandatory arguments
    if not shelfmanager:
        print("ERROR!. Must specify a shelfmanager.")
        exit()

    # Check if shelfmanager is online
    print("Trying to ping the shelfmanager '{}'...".format(shelfmanager))
    try:
       dev_null = open(os.devnull, 'w')
       subprocess.check_call(["ping", "-c2", shelfmanager], stdout=dev_null, stderr=dev_null)
       print("    shelfmanager is online")
       print("")
    except subprocess.CalledProcessError:
       print("    ERROR: shelfmanager can't be reached!")
       exit()

    # Use the shelfmanager as EPICS prefix, unless a different one
    # was defined by the user
    if not epics_prefix:
        epics_prefix=shelfmanager

    # Start the ATCA IPMI monitor
    ipmi = AtcaIpmiMonitor(shelfmanager=shelfmanager)

    # Create the ATCA crate root object
    root = AtcaCrateRoot(ipmi=ipmi)
    root.start()

    # Create the EPICS server
    print("Starting EPICS server using prefix \"{}\"".format(epics_prefix))
    epics = pyrogue.protocols.epics.EpicsCaServer(base=epics_prefix, root=root)
    epics.start()

    # Create the GUI
    if use_gui:
        print("Starting GUI...\n")
        app_top = pyrogue.gui.application(sys.argv)
        app_top.setApplicationName("IPMI monitor for {}".format(shelfmanager))
        gui_top = pyrogue.gui.GuiTop(group='GuiTop')
        gui_top.resize(800, 1000)
        gui_top.addTree(root)

        try:
            app_top.exec_()
        except KeyboardInterrupt:
            # Catch keyboard interrupts while the GUI was open
            pass

        print("GUI was closed...")
    else:
        # Stop the server when Crtl+C is pressed
        print("")
        print("Running without GUI. Press Ctrl+C to stop...")
        try:
            # Wait for Ctrl+C
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

        print("Closing server...")

    epics.stop()
    root.stop()
