#!/usr/bin/env python3

import pyipmi
import pyipmi.interfaces
import time
import threading
from datetime import datetime
from array import array
import pyrogue

class AtcaIpmiMonitorBase():
    """
    Base class used to poll device sensor data in an ATCA crate via IPMI.

    Derived classes must start a pooling thread during __init__(). This thread
    must periodically read sensor data and update the sensor dictionary accordingly.

    Args:
        shelfmanager (str): The node name of the ATCA shelfmanager.
        min_period(float): The minimum number of seconds allowed between polls (default = 5).
                           Must be a positive number.

    """

    def __init__(self, shelfmanager, min_period=-1.0):

        # Add Logger
        self._log = pyrogue.logInit(cls=self)

        # Set the maximum poll interval
        if min_period >= 0:
            self.min_poll_period = min_period
        else:
            self.min_poll_period = 5.0

        # Local variables for debugging purposes
        # - This variables holds the IPMB address of the current IPMI session.
        #   It is used in log messages
        self.ipmb_address = -1

        # Start the IPMI interface
        self.interface = pyipmi.interfaces.create_interface(interface='ipmitool', interface_type='lan')
        self.ipmi = pyipmi.create_connection(self.interface)
        self.ipmi.session.set_session_type_rmcp(host=shelfmanager, port=623)

        # Get sensor list
        full_sensors = {}
        compact_sensors = {}

        # Time stamp of the last IPMI update
        self.timestamp = ''

        # Period of the IPMI poll
        self.poll_period = 0.0

        # List of sensors
        # Dictionary with:
        # * crate -> dictionary of sensors related to the crate
        # * slot -> dictionary of dictionaries of sensor, one entry for each slot
        # Each sensor dictionary is formed by:
        # - name : name of the sensor
        # - type : type of sensor (full or compact)
        # - sensor : sensor object
        # - value : sensor measurement
        self.sensors = {
                'Crate' : {
                    'fans' : {},
                    },
                'Slots' : {}
                }

    def _open_target(self, ipmb_address):
        """
        Establish an IPMI session to the target.

        Args:
            ipmb_address (int): IPMB address of the target.

        Returns:
            None
        """
        try:
            self.ipmi.target = pyipmi.Target(ipmb_address=ipmb_address)
            self.ipmi.session.establish()
            # Update the current opened IPMB address
            self.ipmb_address=ipmb_address
        except pyipmi.errors.CompletionCodeError as e:
            self._log.error("IPMI returned with completion code 0x{:02x} while trying to establish connection to IPMB address = 0x{:02x}".format(ie.cc, ipmb_address))
            self.ipmb_address=-1
            return
        except pyipmi.errors.IpmiTimeoutError as e:
            self._log.error("IPMI Timeout Error while trying to establish connection to IPMB address = 0x{:02x}).".format(ipmb_address))
            self.ipmb_address=-1

    def _scan_sensors(self, keys):
        """
        Scan for sensors on 'ipmb_address'. The resulting sensors
        will be added to the self.sensors dictionary.

        Args:
            keys (list): list of key describing the location of the self.sensors
                          where to add the list of sensors found.

        Returns:
            None.

        Notes:
            Before calling this method, a session must has already been opened
            by calling the method _open_target(ipmb_address)
        """

        self._log.info('Scanning for sensors on IPMB 0x{:02x}...'.format(self.ipmb_address))

        # Point to the device on the sensors dictionary based on the keys
        d = self.sensors
        for k in keys:
            d = d[k]

        try:
            # Verify if the target supports sdr entries
            device_id = self.ipmi.get_device_id()

            # Get the sdr entries
            iter_fct = self.ipmi.device_sdr_entries

            if not device_id.supports_function('sensor'):
                self._log.warning("This target doesn't support SDR entries.")
                return
        except pyipmi.errors.CompletionCodeError as e:
            self._log.error("IPMI returned with completion code 0x{:02x} Error for this device (IPMB address = 0x{:02x})".format(ie.cc, self.ipmb_address))
            return
        except pyipmi.errors.IpmiTimeoutError as e:
            self._log.error("IPMI Timeout Error for this device (IPMB address = 0x{:02x}).".format(self.ipmb_address))
            return

        # Iterate over the sdr entries and look for sensors
        for s in iter_fct():
            try:
                # Full sensors
                if s.type is pyipmi.sdr.SDR_TYPE_FULL_SENSOR_RECORD:
                    name = ''.join("%c" % b for b in s.device_id_string).replace(" ","_")
                    (value, states) = self.ipmi.get_sensor_reading(s.number)
                    if value is not None:
                        # Add the sensor to the list
                        d[name] = { 'type' : 'full', 'sensor' : s, 'value' : s.convert_sensor_raw_to_value(value) }
                # Compact sensors
                elif s.type is pyipmi.sdr.SDR_TYPE_COMPACT_SENSOR_RECORD:
                    name = ''.join("%c" % b for b in s.device_id_string).replace(" ","_")
                    (value, states) = self.ipmi.get_sensor_reading(s.number)
                    # Add the sensor to the list
                    d[name] = { 'type' : 'compact', 'sensor' : s, 'value' : value }
                # Look for fan trays, which are of type 'SDR_TYPE_FRU_DEVICE_LOCATOR_RECORD'
                # and name has 'FanTray' in it.
                # Maybe there is a better way to find fans.
                elif s.type is pyipmi.sdr.SDR_TYPE_FRU_DEVICE_LOCATOR_RECORD:
                    name = ''.join("%c" % b for b in s.device_id_string).replace(" ","_")
                    if 'FanTray' in name:
                        d['fans'][name] = {
                                'speed_level' : { 'fru_id': s.fru_device_id , 'value': 0 },
                                'minimum_speed_level' : { 'value' : 0 },
                                'maximum_speed_level' : { 'value' : 0 }
                                }
            except pyipmi.errors.CompletionCodeError as e:
                self._log.error("IPMI returned with completion code 0x{:02x} Error for this device (IPMB address = {})".format(ie.cc, self.ipmb_address))
                return
            except pyipmi.errors.IpmiTimeoutError as e:
                self._log.error("IPMI timeout error while scanning this device (IPMB address = {})".format(self.ipmb_address))

        self._log.info("Done! {} sensors found.".format(len(d)))

    def _search_sensors(self, keys):
        """
        Search for sensors defined in the self.sensors dictionary in the target.

        Args:
            keys (list): list of key describing the location of the self.sensors
                         where the sensor to search for are defined.

        Returns:
            None.

        Notes:
            Before calling this method, a session must has already been opened
            by calling the method _open_target(ipmb_address)
        """

        self._log.info('Searching for sensors on IPMB 0x{:02x}...'.format(self.ipmb_address))

        # Point to the device on the sensors dictionary based on the keys
        d = self.sensors
        for k in keys:
            d = d[k]

        try:
            # Verify if the target supports sdr entries
            device_id = self.ipmi.get_device_id()

            # Get the sdr entries
            iter_fct = self.ipmi.device_sdr_entries

            if not device_id.supports_function('sensor'):
                self._log.warning("This target doesn't support SDR entries.")
                return
        except pyipmi.errors.CompletionCodeError as e:
            self._log.error("IPMI returned with completion code 0x{:02x} Error for this device (IPMB address = 0x{:02x})".format(ie.cc, self.ipmb_address))
            return
        except pyipmi.errors.IpmiTimeoutError as e:
            self._log.error("IPMI Timeout Error for this device (IPMB address = 0x{:02x}).".format(self.ipmb_address))
            return

        # Sensor found counter
        count = 0

        # Iterate over the sdr entries and look for sensors
        for s in iter_fct():
            try:
                # Get the sensor name
                name = ''.join("%c" % b for b in s.device_id_string).replace(" ","_")
                # Verify if this sensor is defined in the sensor dictionary
                if name in d:
                    # Check if the sensor type is supported
                    if s.type is pyipmi.sdr.SDR_TYPE_FULL_SENSOR_RECORD:
                        d[name]['type'] = 'full'
                    elif s.type is pyipmi.sdr.SDR_TYPE_COMPACT_SENSOR_RECORD:
                        d[name]['type'] = 'compact'
                    else:
                        # Omit sensors of unsupported type
                        continue

                    # We found the sensor. Add it to the dictionary
                    d[name]['sensor'] = s

                    # Increase sensor found counter
                    count = count + 1

            except pyipmi.errors.CompletionCodeError as e:
                self._log.error("IPMI returned with completion code 0x{:02x} Error for this device (IPMB address = {})".format(ie.cc, self.ipmb_address))
                return
            except pyipmi.errors.IpmiTimeoutError as e:
                self._log.error("IPMI timeout error while scanning this device (IPMB address = {})".format(self.ipmb_address))
                return

        self._log.info("Done! {} sensors found.".format(count))

    def get_sensors(self, keys):
        """
        Get the sensors dictionary starting at the location described
        by the specified list of keys.

        Args:
            keys (list): list of key describing the location to return.

        Returns:
            dict: A dictionary with sensors on the specified location.
        """

        # Point to the device on the sensors dictionary based on the keys
        d = self.sensors
        for k in keys:
            d = d[k]

        return d

    def get_sensor_value(self, keys):
        """
        Get the a sensor value. The sensor location is described
        by the specified list of keys.

        Args:
            keys (list): list of key describing the location of the sensors

        Returns:
            The sensor read value, from its dictionary. It can be a string,
            integer, or float, depending on the sensor.
        """

        # Point to the device on the sensors dictionary based on the keys
        d = self.sensors
        for k in keys:
            d = d[k]

        # If the value is a float, truncate it to 2 decimals
        if type(d['value']) is float:
            return round(d['value'], 2)
        else:
            return d['value']

    def _read_sensor(self, sensor):
        """
        Read a value from a sensor.

        Args:
            sensor (object): dictionary with information about the sensor

        Returns:
            The value read from the sensor. It can be a string, integer, or
            float, depending on the sensor.

        Notes:
            Before calling this method, a session must has already been opened
            by calling the method _open_target(ipmb_address)
        """
        try:
            # Check if the sensor object exist.
            if not sensor['sensor']:
                return 0

            (value, states) = self.ipmi.get_sensor_reading(sensor['sensor'].number)
            if value is not None:
                if sensor['type'] == "full":
                    return sensor['sensor'].convert_sensor_raw_to_value(value)
                else:
                    return  value
        except pyipmi.errors.CompletionCodeError as e:
            self._log.error("IPMI returned with completion code 0x{:02x} while reading sensor number {} at IPMB address {}.".format(ie.cc, sensor['sensor'].number, self.ipmb_address))
            return 0
        except pyipmi.errors.IpmiTimeoutError as e:
            self._log.error("IPMI Timeout Error while reading sensor number {} at IPMB address {}.".format(sensor['sensor'].number, self.ipmb_address))
            return 0

    def _read_amc_eeprom(self, bay):
        """
        Extract the FRU information from the AMC EEPROM.

        Args:
            bay (int): Bay number.

        Returns:
            dict: FRU information.

        Notes:
            Before calling this method, a session must has already been opened
            by calling the method _open_target(ipmb_address)
        """
        # Mapping of data in the AMC EEPROM
        mem_map = {}
        mem_map['Product_Mfg_Name']    = { 'marker': b'\xc0', 'step': 2, 'format': '%c'   }
        mem_map['Product_Part_Number'] = { 'marker': b'\xc3', 'step': 1, 'format': '%c'   }
        mem_map['Product_Version']     = { 'marker': b'\x08', 'step': 1, 'format': '%c'   }
        mem_map['Product_Serial_No']   = { 'marker': b'\xe0', 'step': 1, 'format': '%02x' }
        mem_map['Product_Asset_Tag']   = { 'marker': b'\x00', 'step': 1, 'format': '%c'   }

        # Read the EEPROM memory
        eeprom = bytearray()
        for j in range(10):
            resp = self.ipmi.raw_command(lun=0,netfn=0x34,raw_bytes=array('B', [0xfc, bay, j*16, 16]).tostring())

            if resp[0] != 0:
                self._log.error("Error while trying to read the AMC EEPROM on IPMB address {}, bay {}. Got error code: 0x{:02x}".format(self.ipmb_address, bay, resp[0]))
                return

            eeprom = eeprom + resp[1:]

        # Extract the information from the EEPROM dump into the sensor dictionary
        fru_data = {}
        s1 = 0x4c
        s2 = 0
        for k,v in mem_map.items():
            s2 = eeprom.find(v['marker'], s1)
            fru_data[k] = { 'value': ''.join(v['format'] % b for b in array('B', eeprom[s1:s2])) }
            s1 = s2 + v['step']

        return fru_data

    def _read_rtm_eeprom(self):
        """
        Extract the FRU information from the RTM EEPROM.

        Args:
            None

        Returns:
            dict: FRU information.

        Notes:
            Before calling this method, a session must has already been opened
            by calling the method _open_target(ipmb_address)
        """
        # Mapping of data in the AMC EEPROM
        mem_map = {}
        mem_map['Product_Mfg_Name']    = { 'marker': b'\xd3', 'step': 1, 'format': '%c'   }
        mem_map['Product_Name']        = { 'marker': b'\xd1', 'step': 1, 'format': '%c'   }
        mem_map['Product_Part_Number'] = { 'marker': b'\xc3', 'step': 1, 'format': '%c'   }
        mem_map['Product_Version']     = { 'marker': b'\x08', 'step': 1, 'format': '%c'   }
        mem_map['Product_Serial_No']   = { 'marker': b'\xe0', 'step': 1, 'format': '%02x' }
        mem_map['Product_Asset_Tag']   = { 'marker': b'\x00', 'step': 1, 'format': '%c'   }

        # Read the EEPROM memory
        eeprom = bytearray()
        for j in range(16):
            resp = self.ipmi.raw_command(lun=0,netfn=0x34,raw_bytes=array('B', [0x0b, 0, j*16, 16]).tostring())

            if resp[0] != 0:
                self._log.error("Error while trying to read the AMC EEPROM on IPMB address {}, bay {}. Got error code: 0x{:02x}".format(self.ipmb_address, bay, resp[0]))
                return

            eeprom = eeprom + resp[1:]

        # Extract the information from the EEPROM dump into the sensor dictionary
        fru_data = {}
        s1 = 0x74
        s2 = 0
        for k,v in mem_map.items():
            s2 = eeprom.find(v['marker'], s1)
            fru_data[k] = { 'value': ''.join(v['format'] % b for b in array('B', eeprom[s1:s2])) }
            s1 = s2 + v['step']

        return fru_data


    def _read_id(self, slot, bay):
        """
        Read the device ID.

        Args:
            slot (int): Slot number.
            bay (int): the bay number:
                           0 : AMC on bay 0
                           2 : AMC on bay 2
                           4 : Carrier
                           5 : RTM

        Returns:
            str: The device ID. Or empty string if an IPMI error is found.

        Notes:
            Before calling this method, a session must has already been opened
            by calling the method _open_target(ipmb_address)
        """
        try:
            id = self.ipmi.raw_command(lun=0,netfn=0x34,raw_bytes=array('B', [0x05, bay]).tostring())
            if id[0] == 0:
                return  ''.join('%02x' % b for b in array('B', id[1:]))
            else:
                # An error code will happen when an AMC or RTM is not present, which is common.
                # So, use a warning message instead of an error.
                self._log.warning("IPMI raw command returned error code 0x{:02x} while reading ID for slot {} bay {}".format(id[0], slot, bay))
                return ''
        except pyipmi.errors.CompletionCodeError as e:
            self._log.error("IPMI returned with completion code 0x{:02x} while reading ID for slot {} bay {}".format(ie.cc, slot, bay))
            return ''
        except pyipmi.errors.IpmiTimeoutError as e:
            # A timeout will happen when a device (carrier, AMC, or RTM) is not present, which is common.
            # So, use a warning message instead of an error.
            self._log.warning("IPMI Timeout Error while reading ID for slot {} bay {}.".format(slot, bay))
            return ''

    def set_sensor_cb(self, keys, function):
        """
        Set a callback function for the sensor value update.

        Args:
            keys (list): list of key describing the location of the sensors.
            function (function pointer): callback function.

        Returns:
            None.

        Note: The callback function must accept and argument 'value', for the
        sensor value.
        """

        # Point to the device on the sensors dictionary based on the keys
        d = self.sensors
        for k in keys:
            d = d[k]

        d['callback'] = function

    def get_timestamp(self):
        """
        Get the IPMI last update time stamp

        Args:
            None.

        Returns:
            str: The timestamp.
        """
        return self.timestamp

    def get_pollperiod(self):
        """
        Get the last IPMI update period.

        Args:
            None.

        Returns:
            float: time period in seconds
        """
        return self.poll_period

    def get_min_poll_period(self):
        """
        Get the minimum allowed poll period between IPMI updates

        Args:
            None.

        Returns:
            float: the minimum poll period (seconds)
        """
        return self.min_poll_period

    def set_min_poll_period(self, period):
        """
        Set the minimum allowed poll period between IPMI updates

        Args:
            period (float): the minimum poll period (seconds).
                            Must be a positive number.

        Returns:
            None.
        """
        if (period >= 0.0):
            self.min_poll_period = period


class AtcaIpmiStaticMonitor(AtcaIpmiMonitorBase):
    """
    This class polls all the device sensors in an ATCA crate via IPMI.

    The list of sensors for each carrier board in the caret is statically
    defined, including all the known sensors.

    The sensors for the crate itself is dynamically create at startup by
    scanning the sensors available in the crate.

    Args:
        shelfmanager (str): The node name of the ATCA shelfmanager.
        min_period(float): The minimum number of seconds allowed between polls (default = 5).
                           Must be a positive number.
    """
    def __init__(self, shelfmanager, min_period=-1.0):

        # Call the base class __init__() method
        super().__init__(shelfmanager=shelfmanager, min_period=min_period)

        for i in range(2,8):
            self.sensors['Slots'][i] = {
                'ID':               { 'value': ''  },
                'Hot_Swap':         { 'type': '', 'sensor': None, 'value': 0.0 },
                'IPMB_Physical':    { 'type': '', 'sensor': None, 'value': 0.0 },
                'Version_change':   { 'type': '', 'sensor': None, 'value': 0.0 },
                'BoardTemp:RTM':    { 'type': '', 'sensor': None, 'value': 0.0 },
                'BoardTemp:FPGA':   { 'type': '', 'sensor': None, 'value': 0.0 },
                'JunctionTemp:FPG': { 'type': '', 'sensor': None, 'value': 0.0 },
                'BoardTemp:AMC0':   { 'type': '', 'sensor': None, 'value': 0.0 },
                'BoardTemp:AMC2':   { 'type': '', 'sensor': None, 'value': 0.0 },
                'RTM_Hot_Swap':     { 'type': '', 'sensor': None, 'value': 0.0 },
                'AMC_0_Vok':        { 'type': '', 'sensor': None, 'value': 0.0 },
                'AMC_2_Vok':        { 'type': '', 'sensor': None, 'value': 0.0 },
                'FPGA_Vok':         { 'type': '', 'sensor': None, 'value': 0.0 },
                'AMC_0_+12V_Cur':   { 'type': '', 'sensor': None, 'value': 0.0 },
                'AMC_2_+12V_Cur':   { 'type': '', 'sensor': None, 'value': 0.0 },
                'FPGA_+12V_Cur':    { 'type': '', 'sensor': None, 'value': 0.0 },
                'RTM_+12V_Cur':     { 'type': '', 'sensor': None, 'value': 0.0 },
                'AMC_0_+12V_ADIN':  { 'type': '', 'sensor': None, 'value': 0.0 },
                'AMC_2_+12V_ADIN':  { 'type': '', 'sensor': None, 'value': 0.0 },
                'FPGA_+12V_ADIN':   { 'type': '', 'sensor': None, 'value': 0.0 },
                'RTM_+12V_ADIN':    { 'type': '', 'sensor': None, 'value': 0.0 },
                'AMCs': {},
                'RTM': {
                    'ID':                   { 'value': '' },
                    'Product_Mfg_Name':     { 'value': '' },
                    'Product_Name':         { 'value': '' },
                    'Product_Part_Number':  { 'value': '' },
                    'Product_Version':      { 'value': '' },
                    'Product_Serial_No':    { 'value': '' },
                    'Product_Asset_Tag':    { 'value': '' }
                }
            }

            for j in [0,2]:
                self.sensors['Slots'][i]['AMCs'][j] = {
                    'ID':                   { 'value': '' },
                    'Product_Mfg_Name':     { 'value': '' },
                    'Product_Part_Number':  { 'value': '' },
                    'Product_Version':      { 'value': '' },
                    'Product_Serial_No':    { 'value': '' },
                    'Product_Asset_Tag':    { 'value': '' }
                }


        # This flag indicates if we need to search for the sensors
        # defined in the sensor dictionary in each slot
        self.need_search_sensors = {}
        # Initially we need to look for sensors in all slots
        for i in range(2,8):
            self.need_search_sensors[i] = True

        # Scan sensor for the crate
        self._open_target(ipmb_address=0x20)
        self._scan_sensors(['Crate'])

        # Start the polling thread in the background
        self.poll_thread = threading.Thread(target = self._polling)
        self.poll_thread.daemon = True
        self.poll_thread.start()

    def _polling(self):
        """
        Polling function. This function runs in an independent thread, and cyclically
        read all the sensor in the ATCA system, and update the values in the sensor
        dictionary.

        Args:
            None.

        Returns:
            None.
        """

        self._log.info("Starting IPMI Polling thread...")

        now = time.time()

        while True:
            # Set a timestamp of the current reading
            self.timestamp = datetime.now()

            # Read information about the crate
            self._open_target(0x20)
            for n,s in self.sensors['Crate'].items():
                if n == 'fans':
                    for fn,sn in s.items():
                        fru_id = sn['speed_level']['fru_id']
                        sn['speed_level']['value'] = self.ipmi.get_fan_level(fru_id)[0]
                        sn['minimum_speed_level']['value'] = self.ipmi.get_fan_speed_properties(fru_id).minimum_speed_level
                        sn['maximum_speed_level']['value'] = self.ipmi.get_fan_speed_properties(fru_id).maximum_speed_level
                else:
                    s['value'] = self._read_sensor(s)

                # Call callback function, if any
                if 'callback' in s and s['callback'] is not None:
                    s['callback'](value = s['value'])

            ## Read information of devices on each slot
            for i in range(2,8):
                # Open a connection to the specific slot IPMC
                self._open_target(0x80+2*i)

                # Try to read the Carrier ID
                id = self._read_id(slot=i, bay=4)
                self.sensors['Slots'][i]['ID']['value'] = id
                if id:
                    # If a valid ID was read, read the sensors

                    # Check if we need to search for the sensors in this slot.
                    # We will read the IDs as well.
                    if self.need_search_sensors[i]:

                        # Search the sensor in this slot
                        self._search_sensors(['Slots', i])

                        # We don't need to search the sensor in the next cycle
                        self.need_search_sensors[i] = False

                        # Read the AMCs IDs
                        for j in [0,2]:
                            id = self._read_id(slot=i, bay=j)
                            self.sensors['Slots'][i]['AMCs'][j]['ID']['value'] = id
                            if id:
                                # If valid ID is read, read the info from the EEPROM
                                self.sensors['Slots'][i]['AMCs'][j].update(self._read_amc_eeprom(j).copy())

                        # Read the RTM ID
                        id = self._read_id(slot=i, bay=5)
                        self.sensors['Slots'][i]['RTM']['ID']['value'] = id
                        if id:
                            # If a valid ID is read, read the info from the EEPROM
                            self.sensors['Slots'][i]['RTM'].update(self._read_rtm_eeprom())

                    # Read the sensors in this carrier
                    for n,s in self.sensors['Slots'][i].items():
                        try:
                            if n not in ['ID', 'RTM', 'AMCs']:
                                self.sensors['Slots'][i][n]['value'] = self._read_sensor(s)
                        except pyipmi.errors.IpmiTimeoutError:
                            self._log.error("IPMI TImeout error when trying to read slot # {}, {}".format(i, n))
                else:
                    # If we don't read a valid ID, we will need to search for sensors
                    # on the cycle we read a valid ID.
                    self.need_search_sensors[i] = True

            # Update the poll period
            self.poll_period = time.time() - now
            now = time.time()

            # If the period was lower that the minimum period,
            # wait for the remaining of time
            if self.poll_period < self.min_poll_period:
                time.sleep(self.min_poll_period - self.poll_period)


class AtcaIpmiDynamicMonitor(AtcaIpmiMonitorBase):
    """
    This class polls all the device sensors in an ATCA crate via IPMI.

    The list of sensor is dynamically create at startup by scanning the sensors
    available in the crate and on each carrier board in the crate.

    Args:
        shelfmanager (str): The node name of the ATCA shelfmanager.
        min_period(float): The minimum number of seconds allowed between polls (default = 5).
                           Must be a positive number.
    """
    def __init__(self, shelfmanager, min_period=-1.0):

        # Call the base class __init__() method
        super().__init__(shelfmanager=shelfmanager, min_period=min_period)

        for i in range(2,8):
            self.sensors['Slots'][i] = {}

        # Scan sensors
        # - Sensor for the crate
        self._open_target(ipmb_address=0x20)
        self._scan_sensors(['Crate'])
        # - Sensors for each slot
        for i in range(2,8):
            self._open_target(ipmb_address=0x80+2*i)

            # Try to read the Carrier ID
            id = self._read_id(slot=i, bay=4)
            if id:
                # If a valid ID was read, add it to the sensor dict
                self.sensors['Slots'][i]['ID'] = { 'value': id }

                # Now, try to read the AMCs IDs
                for j in [0,2]:
                    id = self._read_id(slot=i, bay=j)
                    if id:
                        # If valid IDs are read, add them to the sensor dict
                        if 'AMCs' not in self.sensors['Slots'][i]:
                            self.sensors['Slots'][i]['AMCs'] = {}
                        self.sensors['Slots'][i]['AMCs'][j] = {}
                        self.sensors['Slots'][i]['AMCs'][j]['ID'] = { 'value': id }
                        self.sensors['Slots'][i]['AMCs'][j].update(self._read_amc_eeprom(j))

                # Finally, try to read the RTM ID
                id = self._read_id(slot=i, bay=5)
                if id:
                    # If a valid ID is read, add it to the sensor list
                    self.sensors['Slots'][i]['RTM'] = {}
                    self.sensors['Slots'][i]['RTM']['ID'] = { 'value': id }
                    self.sensors['Slots'][i]['RTM'].update(self._read_rtm_eeprom())

            # Scan for sensors
            self._scan_sensors(['Slots', i])

        # Start the polling thread in the background
        self.poll_thread = threading.Thread(target=self._polling)
        self.poll_thread.daemon = True
        self.poll_thread.start()

    def _polling(self):
        """
        Polling function. This function runs in an independent thread, and cyclically
        read all the sensor in the ATCA system, and update the values in the sensor
        dictionary.

        Args:
            None.

        Returns:
            None.
        """

        # Add pyrogue logger
        self._log.info("Starting IPMI Polling thread...")

        now = time.time()

        while True:
            # Set a timestamp of the current reading
            self.timestamp = datetime.now()

            # Read information about the crate
            self._open_target(0x20)
            for n,s in self.sensors['Crate'].items():
                if n == 'fans':
                    for fn,sn in s.items():
                        fru_id = sn['speed_level']['fru_id']
                        sn['speed_level']['value'] = self.ipmi.get_fan_level(fru_id)[0]
                        sn['minimum_speed_level']['value'] = self.ipmi.get_fan_speed_properties(fru_id).minimum_speed_level
                        sn['maximum_speed_level']['value'] = self.ipmi.get_fan_speed_properties(fru_id).maximum_speed_level
                else:
                    s['value'] = self._read_sensor(s)

                # Call callback function, if any
                if 'callback' in s and s['callback'] is not None:
                    s['callback'](value = s['value'])

            ## Read information of devices on each slot
            for i in range(2,8):
                # Open a connection to the specific slot IPMC
                self._open_target(0x80+2*i)

                for n,s in self.sensors['Slots'][i].items():
                    try:
                        if n not in ['ID', 'RTM', 'AMCs']:
                            self.sensors['Slots'][i][n]['value'] = self._read_sensor(s)
                    except pyipmi.errors.IpmiTimeoutError:
                        self._log.error("IPMI TImeout error when trying to read slot # {}, {}".format(i, n))

            # Update the poll period
            self.poll_period = time.time() - now
            now = time.time()

            # If the period was lower that the minimum period,
            # wait for the remaining of time
            if self.poll_period < self.min_poll_period:
                time.sleep(self.min_poll_period - self.poll_period)
