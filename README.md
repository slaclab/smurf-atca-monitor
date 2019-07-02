# ATCA monitor via IPMI for the SMuRF Project

## Description

Rogue application which uses IPMI to monitor information from an ATCA system.

The application is formed by a monitor thread which polls sensor information via IPMI periodically from the whole ATCA system. The data is stored in a dictionary file. The dictionary file contains a list of sensor for the crate and for the carrier boards installed in every slot.

The list of sensors for the crate is dynamically created when the application is started, by interrogating the crate for its list of sensors. On the other hand, the list of sensors for the carrier board can be generated in one of two ways:
- Static: in this mode, the list of sensors in each carrier board is statically defined before the application starts, including a list of knows sensors. Because the list is defined before the application starts, it does not reflect the real list of sensors present on the system; however, if carrier boards are added or removed from the crate, the respective sensor data will be updated accordingly on the next poll cycle.
- Dynamic: in this mode, the list of sensors in each carrier board is dynamically created at startup by interrogating each board for its lists of sensors. Because the list is crated during the application's startup, is the hardware changes afterwards (for example is carrier boards are added or removed), the list is not updated; restarting the application will be necessary to obtained an updated list.

Two different classes are defined for each one of these modes: use the class called `AtcaIpmiStaticMonitor` for the static mode or the class called `AtcaIpmiDynamicMonitor` for the dynamic mode.

The pyrogue tree is populate dynamically from the list of sensors in the crate.

## Docker image

When a tag is pushed to this github repository, a new Docker image is automatically built and push to its [Dockerhub repository](https://hub.docker.com/r/tidair/smurf-atca-monitor) using travis.

The resulting docker image is tagged with the same git tag string (as returned by `git describe --tags --always`).

### How to get the container

To get the docker image, first you will need to install the docker engine in you host OS. Then you can pull a copy by running:

```
docker pull tidair/smurf-atca-monitor:TAG
```

Where **TAG** represents the specific tagged version you want to use.

### Running the container

The container runs by default the python script `atca_monitor.py`which takes the following arguments:

```
atca_monitor.py -S|--shelfmanager <shelfmanager> [-e|--epics prefix] [-g|--gui] [-h|--help]

    -S|--shelfmanager <shelfmanager> : Node name of the ATCA shelfmanager.
    -e|--epics        <prefix>       : Start an EPICS server using <prefix> as the PV name prefix.
                                       (default: the shelfmanager node name)
    -g|--gui                         : Start the server with a GUI.
    -h|--help                        : Show this message
```

The command to run the container looks something like this:

```
docker run -ti --rm tidair/smurf-atca-monitor:TAG ARGS
```

where:
- TAG: is the tagged version of the container your want to run,
- ARGS: argument passed to the `atca_monitor.py` script.