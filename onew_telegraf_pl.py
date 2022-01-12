#!/usr/bin/env python

#Gets tempererature from 1-wire DS18B20 sensors and outputs it in format readable by Telegraf
# Called frequently from Telegraf, results are resent to Powerguru and InfluDb

import json
import settings as s
import time
import os
import RPi.GPIO as GPIO # handle Rpi GPIOs for connected to relays
GPIO.setwarnings(False)


# Telegraf plugin
#from typing import Dict
from telegraf_pyplug.main import print_influxdb_format, datetime_tzinfo_to_nano_unix_timestamp

import dateutil.parser
from glob import glob #Unix style pathname pattern expansion
import re
  
# service run on user "telegraf" context, so path will be manipulated 

sensor_settings_filename =  s.replace_path_from_script(s.sensor_settings_filename)
sensor_settings = None


# Function that reads and returns the raw content of 'w1_slave' file
def read_temp_raw(deviceCode):
    w1DeviceFolder = sensor_settings["w1DeviceFolder"]
    f = open(w1DeviceFolder + '/' + deviceCode + '/w1_slave' , 'r')
    lines = f.readlines()
    f.close()
    return lines

# Function that reads the temperature from raw file content
def read_temp(deviceCode):
    # Read the raw temperature data
    lines = read_temp_raw(deviceCode)
    # Wait until the data is valid - end of the first line reads 'YES'
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = read_temp_raw(deviceCode)
    # Read the temperature, that is on the second line
    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        temp_string = lines[1][equals_pos+2:]
        # Convert the temperature number to Celsius
        temp_c = float(temp_string) / 1000.0
        # Return formatted sensor data
        return  deviceCode, temp_c
    
    return None,None
      

def read_thermometers():
    # Get all devices
    w1DeviceFolder = sensor_settings["w1DeviceFolder"]
    w1Devices = glob(w1DeviceFolder + '/*/')
    # Create regular expression to filter only those starting with '28', which is thermometer
    w1ThermometerCode = re.compile(r'28-\d+')
    # Initialize the array
    fields = {}
    # Go through all devices
    for device in w1Devices:
        # Read the device code
        deviceCode = device[len(w1DeviceFolder)+1:-1]
        if deviceCode == "w1_bus_master1":
            continue

        # If the code matches thermometer code add it to the array
        if w1ThermometerCode.match(deviceCode):   
            deviceCode, temp_c = read_temp(deviceCode)
            if deviceCode is not None:
                fields[deviceCode] = temp_c
    # Return the array
    return fields

# this could reset 1-wire if gpio 17 used as bus voltage input
def check_lines():
    global sensor_settings
    w1DeviceFolder = sensor_settings["w1DeviceFolder"]
    for sensor in sensor_settings["sensors"]:
        path = w1DeviceFolder + "/" + sensor["id"]
        if (os.path.isdir(path) == False):
            print ("trying to reset ", path)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(17, GPIO.OUT)
            GPIO.output(17, GPIO.LOW)
            time.sleep(3)
            GPIO.output(17, GPIO.HIGH)
            time.sleep(5)      
    
# report
def onewire_to_telegraf():
    global sensor_settings
      
    
    try:
        with open(sensor_settings_filename) as json_file:
            sensor_settings= json.load(json_file)
    except:
        print ("Cannot find settings file")
        exit(1)
    
    #check_lines()

    thermometer_fields = read_thermometers()
    #print(thermometer_fields)
    
    if not thermometer_fields:
        return False

    measurement = "onewire"
    tag_name = "temperature"

    try:       
            print_influxdb_format(
                measurement=measurement, 
                fields= thermometer_fields,
                tags = {"name" : tag_name},
                nano_timestamp=time.time_ns()
                )
    except:
        pass
  
#print(__file__)
#print(os.path.basename(__file__))
#print(os.path.dirname(__file__))

onewire_to_telegraf() 



         

	