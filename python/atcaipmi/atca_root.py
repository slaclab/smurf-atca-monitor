#!/usr/bin/env python3

import pyrogue

class IpmiThread(pyrogue.Device):
    """
    Device to monitor the status of the IPMI monitor thread

    Args:
        ipmi (obj): the IPMI monitor object.
        name (str): name of this device (Optional. default: IpmiThread).
        description (str): description of this device (Optional. default:
                           "Information about the IPMI thread").

    Returns:
        None.
    """
    def __init__(self, ipmi, name="IpmiThread", description="Information about the IPMI thread", **kargs):
        super().__init__(name=name, description=description, **kargs)

        self.add(pyrogue.LocalVariable(
            name='TimeStamp',
            description='Time stamp of last IPMI query',
            value='',
            mode='RO',
            pollInterval=1,
            localGet= lambda: ipmi.get_timestamp()))

        self.add(pyrogue.LocalVariable(
            name='PollPeriod',
            description='Time period between IPMI polls',
            value=0.0,
            mode='RO',
            pollInterval=1,
            units='s',
            localGet= lambda: round(ipmi.get_pollperiod(),2)))

        self.add(pyrogue.LocalVariable(
            name='MinPollPeriod',
            description='Min allowed time period between IPMI polls',
            value=5.0,
            mode='RW',
            pollInterval=1,
            units='s',
            localGet= lambda: ipmi.get_min_poll_period(),
            localSet= lambda dev, var, value: ipmi.set_min_poll_period(value)))

class BaseDevice(pyrogue.Device):
    """
    Base class use to auto-generate LocalVariables for each sensor
    available.

    Args:
        ipmi (obj): the IPMI monitor object.
        keys (list): list of keys that point to an group of sensors.
        name (str): name of this device.
        description (str): description of this device.

    Returns:
        None.
    """
    def __init__(self, ipmi, keys, name, description, **kargs):
        super().__init__(name=name, description=description, **kargs)

        # Create local variables for each sensor
        # - Get the list of sensors
        d = ipmi.get_sensors(keys=keys)
        # - Add local variables for each sensor
        for n,s in d.items():
            if not 'value' in s:
                # If the dictionary doesn't have the 'value' field,
                # it is a container. Expand it as a new device.
                self.add(BaseDevice(
                    name=str(n),
                    description=str(n),
                    keys=keys+[n],
                    ipmi=ipmi))
            else:
                # Otherwise, it is a value. Add a new variable.
                self.add(pyrogue.LocalVariable(
                    name=n,
                    description=n,
                    value=s['value'],
                    mode='RO',
                    pollInterval=1,
                    localGet= lambda dev, var: ipmi.get_sensor_value(keys=keys+[var.name])))

class AtcaCrateRoot(pyrogue.Root):
    """
    This device describes an ATCA crate. This is the root of this application.

    Args:
        ipmi (obj): the IPMI monitor object.

    Returns:
        None.
    """
    def __init__(self, ipmi, serverPort=0, **kargs):
        super().__init__(name='Crate', description='ATCA crate', serverPort=serverPort, **kargs)

        # Add information about the IPMI thread
        self.add(IpmiThread(ipmi=ipmi))

        # Add all sensors
        self.add(BaseDevice(
            name="Sensors",
            description="Sensors on the crate",
            keys=[],
            ipmi=ipmi))
