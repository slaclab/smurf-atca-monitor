# ATCA monitor via IPMI for the SMuRF Project

## Description

Rogue application which uses IPMI to monitor information from an ATCA system.

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