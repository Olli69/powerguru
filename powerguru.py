#!/usr/bin/env python
# coding: utf-8 
from multiprocessing.dummy.connection import families
from pickle import NONE
import traceback #error reporting
import sys
import json
import os
import signal
#from threading import Thread
from enum import Enum

import settings as s

import subprocess
import time
import pytz #time zone
import random
import re #regular expression
from glob import glob #Unix style pathname pattern expansion

from datetime import datetime, timezone,date, timedelta


#aiohttp
# sudo -H pip3 install aiohttp aiohttp-sse
import asyncio
from aiohttp import web
from aiohttp.web import Response
from aiohttp_sse import sse_response

from aiohttp_session import get_session, SimpleCookieStorage, session_middleware  #pip3 install aiohttp_session[secure]
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from aiohttp_basicauth_middleware import basic_auth_middleware
import hashlib


from datetime import datetime

import socket

from threading import Thread, current_thread
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS


# need to know, if RPI gpio modules should be imported
settings = s.read_settings(s.powerguru_file_name) 
localChannelsEnabled = settings["localChannelsEnabled"]

if localChannelsEnabled:
    import RPi.GPIO as GPIO # handle Rpi GPIOs for connected to relays
    GPIO.setwarnings(False)
    #use GPIO-numbers to refer GPIO pins
    GPIO.setmode(GPIO.BCM)



import pprint
pp = pprint.PrettyPrinter(indent=4)


data_updates = {}
gridenergy_data = None
temperature_data = None
dayahead_list = None 
forecastpv_list = None
current_states = None

netPreviousTotalEnergyPeriod = -999
netPreviousTotalEnergy = -1
netEnergyInPeriod = 0 
netPeriodMeasurementCount = 0

sensor_settings = None
states = None
channels_list = None

# global variables
channels = []
sensorData = None

#init config class
powerGuru = None   






def aggregate_dayahead_prices():
    global dayahead_list,  powerGuru
    # Aggregate day-ahead prices
    energyPriceSpot = None
    if dayahead_list is not None:
        for price_entry in dayahead_list:
            if price_entry["timestamp"] < time.time() and price_entry["timestamp"] > time.time()-3600:
                energyPriceSpot = price_entry["fields"]["energyPriceSpot"]
                powerGuru.set_variable("energyPriceSpot" , round(energyPriceSpot,2))


    # now calculate spot price rank of current hour in different window sizes
    for bCode in powerGuru.dayaheadWindowBlocks:
        rank = get_current_period_rank(bCode)
        if rank is not None:
            variable_code = s.spot_price_variable_code.format(bCode)
            powerGuru.set_variable(variable_code , rank)

def aggregate_dayahead_prices_timeser(start,end):
    #VAATII TESTAUSTA 
    global dayahead_list,  powerGuru
    
    for time in range(start, end+1, powerGuru.nettingPeriodMinutes*60):
        # Aggregate day-ahead prices
        energyPriceSpot = None
        if dayahead_list is not None:
            for price_entry in dayahead_list:
                if price_entry["timestamp"] <= time and  time< price_entry["timestamp"]+3600: # 60 minutesperiod
                    energyPriceSpot = price_entry["fields"]["energyPriceSpot"]
                    powerGuru.set_variable_timeser("energyPriceSpot",time,round(energyPriceSpot,2))

        # now calculate spot price rank of current hour in different window sizes
        for bCode in powerGuru.dayaheadWindowBlocks:
            rank = get_period_rank_timeser(time,bCode)
            if rank is not None:
                variable_code = s.spot_price_variable_code.format(bCode)
                powerGuru.set_variable_timeser(variable_code,time,rank)

        

def aggregate_solar_forecast():
    global forecastpv_list, powerGuru
    blockSums = {}
    for bCodei in powerGuru.solarForecastBlocks:
        blockSums[str(bCodei)] = 0

    if forecastpv_list is not None:
        for fcst_entry in forecastpv_list:
            for bCodei in powerGuru.solarForecastBlocks:
                futureHours = bCodei        
                if fcst_entry["timestamp"] < time.time()+(futureHours*3600):
                    blockSums[str(bCodei)] += fcst_entry["fields"]["pvrefvalue"]

    for sfbCode,sfb in blockSums.items():  
        blockCode = s.solar_forecast_variable_code.format(sfbCode)
        powerGuru.set_variable(blockCode , round(sfb,2))


def aggregate_solar_forecast_timeser(start,end):
    #TESTATTAVA
    global forecastpv_list, powerGuru

    for time in range(start, end+1, powerGuru.nettingPeriodMinutes*60):
        blockSums = {}
        for bCodei in powerGuru.solarForecastBlocks:
            blockSums[str(bCodei)] = 0

        if forecastpv_list is not None:
            for fcst_entry in forecastpv_list:
                for bCodei in powerGuru.solarForecastBlocks:
                    futureHours = bCodei        
                    if fcst_entry["timestamp"] < time+(futureHours*3600):
                        blockSums[str(bCodei)] += fcst_entry["fields"]["pvrefvalue"]

        for sfbCode,sfb in blockSums.items():  
            blockCode = s.solar_forecast_variable_code.format(sfbCode)
            powerGuru.set_variable_timeser(blockCode,time,round(sfb,2))




#helper for setting gpio
def setOutGPIO(gpio,enable,init=False):
    global channels_list
    #enable: True ->GPIO.HIGH, False -> GPIO.LOW
    if init:
        GPIO.setup(gpio, GPIO.OUT) 
         
    GPIO.output(gpio,GPIO.HIGH if enable else GPIO.LOW)
    
    """
    for channel_row in channels_list:
        if channel_row["gpio"]==gpio:
            channel_row["enabled"] = enable
            break
    """
    
    """
    for channel in channels:
        if channel.gpio==gpio:
            channel.up = enable
            break

     """       
     
 
# This class handles line resources (phases) e.g.
#TODO; disabling line capacity handling
class PowerGuru:
    def __init__(self,init_file_name):
        self.settings = s.read_settings(init_file_name) 
        #add most important settings to attributes
        self.maxLoadPerPhaseA = self.get_setting("maxLoadPerPhaseA")
        self.nettingPeriodMinutes = self.get_setting("nettingPeriodMinutes")
        self.dayaheadWindowBlocks = self.get_setting("dayaheadWindowBlocks") 
        self.solarForecastBlocks = self.get_setting("solarForecastBlocks") 
        self.localChannelsEnabled = self.get_setting("localChannelsEnabled")
        
        self.lines = [ (1, 0),(2, 0),(3, 0)]
        
        self.lines_sorted = self.lines
        self.status_propagated = True
        self.variables = {}
        self.variables_timeser = {}
    
    def get_current_period_id(self):
        return  int(time.time()/(self.nettingPeriodMinutes*60))

    def get_current_period_start(self):
        return  int(time.time()/(self.nettingPeriodMinutes*60))*(self.nettingPeriodMinutes*60)

    # time series
    # { "type" : "num", "values": {"time": value }}
    def set_variable_timeser(self,field_code,time,value,type = "num"):
        #print("set_variable_timeser:", field_code, time,value)
        if field_code not in self.variables_timeser: # time series exists, use it
            self.variables_timeser[field_code] = {"values": {}, "type" : type}   
        self.variables_timeser[field_code]["values"][str(time)] = value


    def get_values_timeser(self,field_code,time_first=None, time_last=None,states_requested=None):
        if time_first is None:
            time_first = self.get_current_period_start()
        if time_last is None:
            time_last = time_first+24*3600-1
        if field_code not in self.variables_timeser:
            return {}

        return_values = {}
        #print("states_requested", "     ", states_requested)
        for vkey,variable in self.variables_timeser[field_code]["values"].items():
            if str(time_first) <= vkey and vkey <= str(time_last):
                if states_requested is None:
                    return_values[vkey] = variable
                else: #state filter
                    var_out = []
                    for var in variable:
                        if var in states_requested:
                            var_out.append(var)
                       

                    return_values[vkey] = var_out
                    #print(vkey, "     ", var_out)
 
        return return_values


    def get_value_timeser(self,field_code,time,default_value = None):
        if field_code == 'mmdd' or field_code == 'hhmm':
            tz_local = pytz.timezone(powerGuru.get_setting("timeZoneLocal"))
            dt = datetime.fromtimestamp(time, tz_local)
            if field_code == 'mmdd':
                return dt.strftime("'%m%d'")
            elif field_code == 'hhmm':
                return dt.strftime("'%H%M'")
        else:
            if field_code in self.variables_timeser:
                if str(time) in self.variables_timeser[field_code]["values"]:
                    if self.variables_timeser[field_code]["type"] == "str":
                        return "'{}'".format(self.variables[field_code]["values"][str(time)])
                    else:
                        return self.variables_timeser[field_code]["values"][str(time)]
                else:
                    return default_value
            else:
                return default_value


    def set_variable(self,field_code,value):
        self.variables[field_code] = {"value": value, "ts" : time.time(), "type" : "num"}

        
    def get_value(self,field_code,default_value = None):
        #TODO: check if value is expired, expiration in variables settings file .. coming later
        if field_code in self.variables:
            if self.variables[field_code]["type"] == "str":
                return "'{}'".format(self.variables[field_code]["value"])
            else:
                return self.variables[field_code]["value"]
        else:
            return default_value


    def get_setting(self,field_code,default_value = None):
        if field_code in self.settings:
            return self.settings[field_code]
        else:
            return default_value

    # adds pseudo variables like time 
    def get_variables(self):
        return_object = self.variables  
        # pseudo variables date, time etc
        return_object["hhmm"] = {"value": datetime.now().strftime("%H%M"), "ts" : time.time(), "type" : "str"}
        return_object["mmdd"] = {"value": datetime.now().strftime("%m%d"), "ts" : time.time(), "type" : "str"}
        return return_object.items()


    def set_status_unpropagated(self):
        self.status_propagated = False    

    # check if there is enough line capacity in off lines used by the channel
    #TODO: powerW...
    def requestCapacity(self,requested_lines):
        for line in self.lines:
            requested_phase_current = 0
            for rline in requested_lines:
                if rline["l"] == line[0]:
                    requested_phase_current = rline["A"]
            
            projectedOverload = line[1]-self.maxLoadPerPhaseA+requested_phase_current
            if projectedOverload>0:
                print("Line ", line[0], " could cause overload: ", projectedOverload)
                return False
            
        return True
    
    def setLoad(self,importL1A,importL2A,importL3A): # tällä voisi asettaa mittausten luvun jälkeen nykyisen kuorman
        # jos joku ylittää sallitun kuorman voisi käydä katkomassa
        self.lines = [ (1, importL1A),(2, importL2A),(3, importL3A)]
        
        # overload control
        # check each line, if overload -> decrease load (if possible) until no overload exists
        
        for line in self.lines:
            overLoad = line[1]-self.maxLoadPerPhaseA
            if overLoad<0:
                #print("No overload in line ", line,", overload:" ,overLoad)
                continue
            
            for channel in channels:
                channel_lines = []
                for act_line in channel.lines:
                    if act_line.get("l",-1)==line[0] and channel.up:
                        channel.loadDown()
                        print("OVERLOAD, channel {}, line {:d} lowering down, releasing {:f} A".format(channel.code, line[0],act_line["A"] ))
                       
                        
        self.lines_sorted = sorted(self.lines, key=lambda line: line[1])
        print("setLoad")
        pp.pprint(self.lines_sorted)

        return self.lines_sorted
    
    def getLineCapacity(self,reverse=False): # antaa vähiten kuormitetuimmat linjat ekaksi tai jos revrse niin toisin päin
        available_lines = []
        for line in sorted(self.lines, key=lambda line: line[1],reverse=reverse):
            available_lines.append({"l" : line[0],"availableA":self.maxLoadPerPhaseA-line[1]})
        return available_lines #näitä voisi kuormittaa jos ei ole jo kuormitettu

    #for the dashboard
    def get_status(self,set_status_propagated):
        if set_status_propagated:
            self.status_propagated = True  

        tz_utc = pytz.timezone("UTC")
        
        status = {"channels": [], "updates":[], "sensors":[], "variables":[], "current_states":None}

        for idx,channel in enumerate(channels):
            status["channels"].append({ "idx" : idx, "code" : channel.code, "name" : channel.name, "up":  channel.up, "target" : channel.target })
        
        for variable_code,variable in powerGuru.get_variables():
            status["variables"].append({ "code" : variable_code, "value" : variable["value"], "ts":  variable["ts"], "type" : variable["type"] })


        for update_key, update_values in data_updates.items():
            updated_dt = (tz_utc.localize(datetime.utcnow())-update_values["updated"])
            updated_dt = updated_dt - timedelta(microseconds=updated_dt.microseconds) #round
            
            latest_ts_str = datetime.fromtimestamp(update_values["latest_ts"]).strftime("%Y-%m-%dT%H:%M:%S%z") 
            status["updates"].append({ "code" : update_key, "updated" : update_values["updated"].strftime("%Y-%m-%dT%H:%M:%S%z") , "latest_ts":  latest_ts_str })
                
        for sensor in sensorData.sensors:
            status["sensors"].append({ "code" : sensor["code"], "id" : sensor["id"], "name" : sensor["name"], "value":  sensor["value"] })

        if current_states:
            status["current_states"] = current_states

        if gridenergy_data:
            status["Wsys"] = gridenergy_data["fields"]["Wsys"]
        else:
            status["Wsys"] = None
        
        return status


    # this is the main calculation function    
    def recalculate(self):
        print ('#recalculate')
        #global self
        global netEnergyInPeriod, netPreviousTotalEnergy, netPreviousTotalEnergyPeriod,netPeriodMeasurementCount
        global current_states
        global gridenergy_data, temperature_data, dayahead_list, forecastpv_list
    
        
        #todo: check data age
        if gridenergy_data is None or "fields" not in gridenergy_data:
            print("No gridenergy_data")
            return False
        
        #TODO: read from cache , check validity (in init) , handle cases if not used
        #if dayahead_list is None or forecastpv_list is None:
        #    return False

        importTot = 0
        price_fields = {}
        loadsA = [0,0,0]
        
        # Go through all connected thermometers
        
        dtnow = datetime.now()
        tz_local = pytz.timezone(powerGuru.get_setting("timeZoneLocal")) 
        now_local = dtnow.astimezone(tz_local).isoformat()
        
        #TODO: check how often to run
        #get current prices and expected future solar, e.g. solar6h is solar within next 6 hours
        # block updates?, should we get it once a hour
        aggregate_solar_forecast()
    
        loadsA[0] = gridenergy_data["fields"]["AL1"]
        loadsA[1] = gridenergy_data["fields"]["AL2"]
        loadsA[2] = gridenergy_data["fields"]["AL3"]
    
        importTot = gridenergy_data["fields"]["Wsys"]
        cumulativeEnergy = gridenergy_data["fields"]["kWhTOT"]
             
        price_fields[ "sale"]= (-importTot if importTot<0 else 0.0)
        price_fields[ "purchase"]= (importTot if importTot>0 else 0.0)
    
        # sales only for negative import
        price_fields[ "sale"]= (-importTot if importTot<0 else 0.0)
        price_fields[ "purchase"]= (importTot if importTot>0 else 0.0)
            
        #TODO: tarvitaanko, yösähkö erikseen, tää olisi hyvä parametroida
        local_time = now_local[11:19] 
        #TODO nämä parametreistä
        if "07:00:00" < local_time < "22:00:00":# and dtnow.isoweekday()!=7: 
            price_fields[ "purchaseDay"]= (importTot if importTot>0 else 0.0)
            price_fields[ "purchaseNight"]= 0.0
        else:
            price_fields[ "purchaseNight"]= (importTot if importTot>0 else 0.0)
            price_fields[ "purchaseDay"]= 0.0
        
        # new, todo: tähän tallennukset influxiin
        if netPreviousTotalEnergy == -1:
            netPreviousTotalEnergy = cumulativeEnergy
            
        #currentNettingPeriod = int(time.time()/(self.nettingPeriodMinutes*60))
        currentNettingPeriod = self.get_current_period_id()

        if netPreviousTotalEnergyPeriod != currentNettingPeriod:
            # this should probably be run when a new hour (period) starts, not always
            aggregate_dayahead_prices()

            netPreviousTotalEnergyPeriod =  currentNettingPeriod
            netPeriodMeasurementCount = 0 
    #TODO: tsekkaa miksi netEnergyInPeriod nollaantuu viivellä periodin vaihtuessa
        
        netEnergyInPeriod = cumulativeEnergy-netPreviousTotalEnergy
        netPeriodMeasurementCount += 1
        if netPeriodMeasurementCount == 1:
            netPreviousTotalEnergy = cumulativeEnergy
        self.set_variable("netEnergyInPeriod" , round(netEnergyInPeriod,2))
        print(" {} cumulativeEnergy- {} netPreviousTotalEnergy = {} netEnergyInPeriod ".format(cumulativeEnergy,netPreviousTotalEnergy,netEnergyInPeriod))
        
        self.setLoad(loadsA[0],loadsA[1],loadsA[2])             
        current_states = check_states()

        # start channels
        if powerGuru.localChannelsEnabled:
            #TODO: OVERLOAD CONTROL!!!    


            #TODO:miksi eri loopit, randomin takia?, vai jäänne
            for channel in channels:
                target = channel.getTarget(current_states)
                #print(channel.name, " got target: ",target)
            
            random_channels = channels.copy()
            random.seed()
            random.shuffle(random_channels) # set up load in random order
            
            for channel in random_channels:
                target = channel.getTarget(current_states)  
                channels[channel.idx].target = target 
                if target["keep_up"]:
                    #channel.on = True
                    loadChange = channel.loadUp() #
                    if abs(loadChange) > 0: #only 1 v´chnage at one time, eli ei liikaa muutosta minuutissa
                        break
                elif not target["keep_up"] and target["state"]: 
                    loadChange = channel.loadDown()
                    #channel.on = False
                    if abs(loadChange) > 0:
                    # print ("loadDown loadChange:", loadChange)
                        break
    

        self.set_status_unpropagated() # latest status not propagated to clients
        # export to influxDB

        reportState(price_fields)








# Stores sensor values (from thermometers)
class SensorData:
    def __init__(self, sensors):
        self.sensors = []
        for sensor in sensors:
            self.addSensor(sensor["code"],sensor["id"], sensor.get("name",""),False,sensor["type"])
        #pp.pprint(self.sensors)  
    def addSensor(self,code,id,name,enabled,type = "1-wire"):
        self.sensors.append({"code":code,"type": type,"id" : id,"name" :name,"value":None, "enabled" : enabled })

    
    def setEnabledById(self,id,enabled):    
        for sensor in self.sensors:
            if sensor["id"] == id:
                sensor["enabled"]= enabled
                return True
        return False
         
    def setValueById(self,id,value):    
        global powerGuru
        for sensor in self.sensors:
            if sensor["id"] == id:
                sensor["value"]= value
                # set sensor value to variables, so it can be used in states
                powerGuru.set_variable(sensor["code"],round(value,1))
                return
                
    def getValueByCode(self,code):    
        for sensor in self.sensors:
            if sensor["code"] == code:
             #   print ("getValueByCode ",sensor["code"], "  ", sensor["value"] )
                return sensor["value"]
            
        return None

  
class channelType(Enum): #RFU 
    SWITCH = 0 #default 
    TESLA_VEHICLE = 101   # more an idea now, not implemented yet, could send start/stop charging commands via Tesla API
    TESLA_POWERWALL = 102  # see previous

""" Tesla API interface would probably need:
- OAuth authentication
- minimum uptime for the channel (re)
- reading battery state (like temp sensor in boilers) /api/1/vehicles/:id/vehicle_data : response.charge_state.battery_level
"""

# Channel can be e.g. one boiler with 1 or 3 lines (phases)
class Channel:  
    def __init__(self, idx,code, data):
        self.type = channelType.SWITCH #RFU, could be eg. battery system
        self.idx = idx # 0-indexed
        self.code = code #ch + 1-indexed nbr
        self.name = data["name"]
        self.gpio = data["gpio"]
        self.sensor = data.get("sensor",None)
        #self.defaultTarget = data.get("defaultTarget",None)

        

        self.t = data.get("reachedWhen",None)
        self.upIf = data.get("upIf",None)
        
        self.loadW =  data.get("loadW",0)
        self.up = False
        self.reverse_output = data.get("reverse_output",False) #esim. lattialämmityksen poissa-kytkin, todo gpio-handleen
        self.target = None

        lines = []  
        
        if not "lines" in data:
            data["lines"] = [1,2,3]

        if "lines" in data and len(data["lines"])>0:
            current_per_phase = round((self.loadW /s.volts_per_phase)/len(data["lines"]),2)
        else:
            current_per_phase = 0 
            
        for line in  data["lines"]:
            lines.append({'l':line, 'A': current_per_phase}  ) 
        self.lines = lines

        if self.gpio:
            setOutGPIO(self.gpio,self.up,True) #init
            
        """
        self.lines = [{"l" : 1, "gpio" : None, "A" : 0 ,"up": False},{"l" : 2, "gpio" : None, "A" : 0,"up": False },{"l" : 3, "gpio" : None, "A" : 0,"up": False }]
     
        print("LINES A initiated")
        pp.pprint(self.lines)

        for line in data["lines"]:
            ln = {"l" : line["l"], "gpio" : line["gpio"], "A" : line.get("A",0),"up": False }
            lineInd = line["l"]-1 #HUOM INDEKSOINTI
            print("debug:", ln, lineInd)
            self.lines[lineInd] = ln
            
            GPIO.setup(ln["gpio"], GPIO.OUT)
            #TODO:: nyt olisi hyvä hetki ajaa GPIOT alas, jos jääneet ylös ennestään
            GPIO.output(ln["gpio"],GPIO.HIGH if ln["up"] else GPIO.LOW)
        
        print("LINES B")
        pp.pprint(self.lines)
        """ 
        
        self.targets = [] 
        if "targets" in data:
            for target in data["targets"]:
                tn = {"targetStates" : target["targetStates"], "sensor" : target.get("sensor",None), "upIf": target.get("upIf",None),"valueabove": target.get("valueabove",None), "valuebelow": target.get("valuebelow",None), "forceOn" :  target.get("forceOn",None)}
                self.targets.append(tn) 
        """
        print()
        print()
        print("class Channel", self.code) 
        print("lines:",self.lines) 
        print("targets:",self.targets) 
        print()
        print()
        print()
        """
    
    
    def getTarget(self,current_states):
        # get first channel target where state is matching
        for target in self.targets:
#targetStates            
#            if target["state"] in current_states:
            matching_state = None
            if "targetStates" in target:
                for condi in target["targetStates"]:
                    if condi in current_states:
                        matching_state = condi
                        break

            if matching_state:
                if "upIf" in target and target["upIf"] is not None:
                    keep_up,error_in_test = test_formula( target["upIf"],self.name+ ":"  +matching_state  )  
                    if error_in_test: #possibly error in target t, try next one (should we panic and break )
                        #TODO: error in formula (e.g. wrong variable) should be reported somehow to dashboard - error list...
                        continue # try next target
                    else: #found first matching target
                        return {"state" : matching_state,"keep_up":keep_up,"upIf": target["upIf"] }    

        
        return {"state" : None,"keep_up":False} # no matching target
    
    def getLine(self,l):
        for line in self.lines:
            if line["l"] == l:
                return line
        return None
    
    def loadUp(self):
        global powerGuru
        print("loadUp", self.name)
        if powerGuru.requestCapacity(self.lines):
            #print("requestCapacity ok")
            setOutGPIO(self.gpio,True)
            self.up = True
        else:
            print("requestCapacity failed")
        
       
        
        """
        lineResources = powerGuru.getLineCapacity(reverse=False)
        
        for lr in lineResources:
            line = self.getLine(lr["l"])
            #print("line",line)
            if line is not None:
                if not line["up"] and lineResources[ line["l"]-1]["availableA"]>10:
                    print("line {:d} raising up with {:d} A".format(line["l"],line["A"]))
                    line["up"] = True
                    setOutGPIO(line["gpio"],line["up"])
                    print("self.lines after loadUp", self.lines,"lineResources:",lineResources)
                    return line["A"] 
                
        """
        return 0

   
         
    # check if available lines, if not return 0
    # check which line to increase
    #return increased power in A, 0 if nothing to descrease
    
    def loadDown(self):
        #TODO tsekkaa onko yli kapasiteettirajan tai yli tehorajan
        setOutGPIO(self.gpio,False)
        self.up = False
        
        """
        lineResources = powerGuru.getLineCapacity(reverse=True) #katso saisiko ton amppeerimäärän laitteelta
        for lr in lineResources:
            line = self.getLine(lr["l"])
            #print("line",line)
            if line is not None:
                if line["up"]:
                    print("line {:d} lowering down up with {:d} A".format(line["l"],line["A"]))
                    line["up"] = False
                    #lineResources[]
                    setOutGPIO(line["gpio"],line["up"])
                    print("self.lines after loadUp", self.lines,"lineResources:",lineResources)
                    return -line["A"] 
        """
        return 0
    

    # if line defined decrease only if this line is high - load regulation (eli jos vaiheessa ylikuormaa , koskee vain tätä vaihetta)
    # check if current power > 0, if not return 0
    # check which line to decrease
    #return decreased power in A, 0 if nothing to descrease
    
    
#- - - - - - - - -



def sig_handler(signum, frame):
    pass
    exit(1)
    
    
def check_states():
    ok_states = []
    global states
    global powerGuru
  
    #TODO: spotlowesthours - kuluvan päivän x halvinta tuntia, tässä pitäisi kyllä ottaa myös kuluneet
    #voisi ottaa ko päivän kuluneet ja koko tiedetyn tulevaisuuden
    for state_key,state in states.items(): # check 
        #print(state_key,state )
        if "enabledIf" in state:
            state_returned, error_in_test = test_formula( state["enabledIf"],state_key)  
            if state_returned and not error_in_test: 
                ok_states.append(state_key)      

    for state_key,state in states.items(): 
        states[state_key]["enabled"] = (state_key in ok_states)
    print("check_states result:")   
    pp.pprint (ok_states)
    return ok_states

def check_states_timeser(start, end):
    global states
    global powerGuru
    print("aikaväli:",start, end)
    for time in range(start, end+1, powerGuru.nettingPeriodMinutes*60):
        ok_states = []
        for state_key,state in states.items(): # check 
            if "enabledIf" in state:
                state_returned, error_in_test = test_formula_timeser( state["enabledIf"],time)  
                # do not replicate internal states, typically max 999
                if state_returned and not error_in_test and int(state_key)>s.states_internal_max: 
                    ok_states.append(int(state_key))   #Voisi olla kai int tästä    

        #print (time, ok_states)
        powerGuru.set_variable_timeser("states",time,ok_states,"list")

    return 


def test_formula(formula,info):
    #returns: value,isError
    #print("#######")
    eval_string = formula
    # powerguru:time
    for vkey,v in powerGuru.get_variables():
        if vkey in eval_string:
            variable_value = powerGuru.get_value(vkey,None)
            if variable_value is not None:
                eval_string = eval_string.replace(vkey,str(variable_value))
            else:
                print("Variable {} value was None:".format(vkey))
                return False, True
            
    try:
        eval_value = eval(eval_string,{})   
    except NameError:
        print("Variable(s) undefined in " + eval_string)
        return False, True 

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception( exc_type,exc_value, exc_traceback,limit=5, file=sys.stdout)
        print("eval_string: ",eval_string)
        return False, True  

    #print("formula {},  [{}] => {}".format(info,eval_string, eval_value))
    return eval_value, False 


def test_formula_timeser(formula,time,debudError=False):
    global powerGuru
    variable_keys = list(powerGuru.variables_timeser.keys())

    #print(variable_keys)
    #pp.pprint(variable_keys)

    variable_keys.append("hhmm")
    variable_keys.append("mmdd")
    eval_string = formula

    for vkey in variable_keys:
        if vkey in eval_string:
            variable_value = powerGuru.get_value_timeser(vkey,time,None) ########
            if variable_value is not None:
                eval_string = eval_string.replace(vkey,str(variable_value))
            else:
                print("Variable {} value was None:".format(vkey))
                return False, True
            
    try:
        eval_value = eval(eval_string,{})   
    except NameError:
        if debudError:
            print("Variable(s) undefined in " + eval_string)
        return False, True 

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception( exc_type,exc_value, exc_traceback,limit=5, file=sys.stdout)
        print("eval_string: ",eval_string)
        return False, True  

    #print("formula {},  [{}] => {}".format(info,eval_string, eval_value))
    return eval_value, False 


        
def reportState(price_fields): 
    global powerGuru
    state_fields = {}
    channel_fields = {}

    # via Telegraf relay to influxDB
    #TODO: add to parameters
    ifClientUrl = powerGuru.get_setting("InfluxDBClientUrl","http://127.0.0.1:8086")
    ifClientToken = powerGuru.get_setting("InfluxDBClientToken","")

    ifclient = InfluxDBClient(url = ifClientUrl,token=ifClientToken)
    try:
        json_body = []
        
        json_body.append( {
        "measurement": "prices",
        "time":  datetime.now(timezone.utc),
        "fields": price_fields
        })
           
        if powerGuru.localChannelsEnabled:
            for channel in channels:
                channel_fields[channel.code]=  (1 if channel.up else 0)
            json_body.append( {
            "measurement": "channels",
            "time":  datetime.now(timezone.utc),
            "fields": channel_fields
            })

        for state_key,state in states.items(): 
            state_fields[state_key]=  (1 if state["enabled"] else 0)
            
        json_body.append( {
            "measurement": "states",
            "time":  datetime.now(timezone.utc),
            "fields": state_fields
            })

        write_api = ifclient.write_api(write_options=SYNCHRONOUS)
        write_api.write("", "", json_body)

       # print ("Wrote to influx")
    except:
        print ("Cannot write to influx")
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception( exc_type,exc_value, exc_traceback,limit=5, file=sys.stdout)
         
 

def get_spot_sliding_window_periods(current_period_start_ts, window_duration_hours):
    # get entries from now to requested duration in the future, 
    # if not enough future exists, include periods from history to get full window size
    global dayahead_list
    if  dayahead_list is  None:
        return None

    # get max and min
    min_dayahead_time = current_period_start_ts +10*24*3600
    max_dayahead_time = 0
    for price_entry in dayahead_list:
        min_dayahead_time = min(min_dayahead_time,price_entry["timestamp"])
        max_dayahead_time = max(max_dayahead_time,price_entry["timestamp"])      


    window_end_excl = min(current_period_start_ts + window_duration_hours*3600,max_dayahead_time)
    window_start_incl = window_end_excl-window_duration_hours*3600
    #print("current_period_start_ts", current_period_start_ts)
    #print("dayahead_list ts range",min_dayahead_time, max_dayahead_time)
    #print("window_start_incl  -  window_end_excl",window_start_incl, window_end_excl)


    entry_window = []
    for price_entry in dayahead_list:
        if window_start_incl <= price_entry["timestamp"]  and price_entry["timestamp"] < window_end_excl:
            tsstr = datetime.fromtimestamp(price_entry["timestamp"]).strftime("%Y-%m-%dT%H:%M") 
            entry_window.append({"ts":price_entry["timestamp"],"value":round(price_entry["fields"]["energyPriceSpot"],2), "tsstr":tsstr})
          
    entry_window_sorted = sorted(entry_window, key=lambda entry: entry["value"])
    return entry_window_sorted


def get_current_period_rank(window_duration_hours):
    global powerGuru
    period_in_seconds = 60*powerGuru.nettingPeriodMinutes
    current_period_start_ts = int(time.time()/period_in_seconds)*period_in_seconds

    price_window_sorted = get_spot_sliding_window_periods(current_period_start_ts, window_duration_hours)
    rank = 1
    if price_window_sorted is not None:
        for entry in price_window_sorted:
            if current_period_start_ts == entry["ts"]:
                #print("window size hours:", window_duration_hours, ", rank:", rank )
                #pp.pprint(price_window_sorted)
                return rank
            rank += 1
        
    print("****Cannot find current_period_start_ts in the window", current_period_start_ts)
    return None

def get_period_rank_timeser(time, window_duration_hours):
    global powerGuru
    #period_in_seconds = 60*powerGuru.nettingPeriodMinutes
    #current_period_start_ts = int(time.time()/period_in_seconds)*period_in_seconds

    price_window_sorted = get_spot_sliding_window_periods(time, window_duration_hours)
    rank = 1
    if price_window_sorted is not None:
        for entry in price_window_sorted:
            if time == entry["ts"]:
                #print("window size hours:", window_duration_hours, ", rank:", rank )
                #pp.pprint(price_window_sorted)
                return rank
            rank += 1
        
    print("****Cannot find current_period_start_ts in the window", time)
    return None





def load_program_config():
    global actuators,sensorData,thermometers, powerGuru
    global sensor_settings,states #,switches
    global dayahead_list, forecastpv_list
    global channels_list
    
    powerGuru = PowerGuru(s.powerguru_file_name) 

    #TODO: read cached forecast and price info and check validity?

     #1-wire
    sensor_settings = s.read_settings(s.sensor_settings_filename)  
    sensorData = SensorData(sensor_settings["sensors"])



    #channels_list
    if powerGuru.localChannelsEnabled:
        channels_list = s.read_settings(s.channels_filename) 
        for idx,channel in enumerate(channels_list):
            channel =  Channel(idx,"ch"+str(idx+1),channel)
            channels.append(channel)
            
    # states
    states = s.read_settings(s.states_filename) 
    
    # TODO: cache expiration to parameters
    expire_file_cache_h = 8
    dayahead_list,dayahead_mtime = load_data_json(s.dayahead_file_name) 
    if dayahead_list is not None and time.time()-dayahead_mtime>expire_file_cache_h*3600:
        print("Cached {} to old {} hours.".format(s.dayahead_file_name,(time.time()-dayahead_mtime)/3600))
        dayahead_list = None
         
 
    forecastpv_list, forecastpv_mtime = load_data_json(s.forecastpv_file_name) 
    if forecastpv_list is not None and time.time()-forecastpv_mtime>expire_file_cache_h*3600:
        print("Cached {} to old {} hours.".format(s.forecastpv_file_name,(time.time()-forecastpv_mtime)/3600))
        forecastpv_list = None

   
    return None


def load_data_json(file_name):  
    try:
        mtime = os.path.getmtime(file_name)
        with open(file_name) as json_file:
            return json.load(json_file),mtime
    except:
        return None


def save_data_json(field_list,file_name): 
    try:
        with open(file_name, 'w') as outfile:
            json.dump(field_list, outfile)

        return True
    except:
        return False

    


def filtered_fields(field_list,tag_name_value,debug_print=False, save_file_name = ''):
    global data_updates
    tz_utc = pytz.timezone("UTC")
    
    latest_ts = 0
    
    result_set = []
    for field in field_list:
        if "tags" not in field:
            continue
        if "name" not in field["tags"]:
            continue
        if field["tags"]["name"]==tag_name_value:
            result_set.append(field)
            if "timestamp" in field:
                latest_ts = max(latest_ts,field["timestamp"] )

    if len(result_set)>0:
        print("{:s} , fields with tag name {:s} :".format(datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), tag_name_value),end = ' ')        
        if debug_print:
            if result_set:
                print()
                pp.pprint(result_set)
            else:
                print("None")    
            print()
            print()
        else:
            print(str(len(result_set)) + " rows" )
            
        data_updates[tag_name_value] = {"updated" : tz_utc.localize(datetime.utcnow()), "latest_ts" : latest_ts }
 
    if len(result_set)>0 and save_file_name:
        save_data_json(result_set,save_file_name)
    
    return result_set


def process_sensor_data(temperature_data):
    global sensor_settings,sensorData
    found_new_sensors = False
    # check if there are new sensors not found in the sensor settings 
    for data_row in temperature_data:
        for sensor_id,value in data_row["fields"].items():         
            if not sensorData.setEnabledById(sensor_id,  True):
                found_new_sensors = True
                sensor_settings["sensors"].append( {"code":'sensor'+str(len(sensor_settings["sensors"])+1), "type": "1-wire", "id": sensor_id, "name":"Automatically added"})
                #reread
                sensorData = SensorData(sensor_settings["sensors"])
    
    if found_new_sensors: #save
        with open(s.sensor_settings_filename, 'w') as outfile:
            json.dump(sensor_settings, outfile, indent=4) 
       
         
    #now set values    
    for data_row in temperature_data:
        for sensor_id,value in data_row["fields"].items():
            sensorData.setEnabledById(sensor_id,  True) #onko enable tarpeen?
            sensorData.setValueById(sensor_id,value)  
                      


#aiohttp

def create_channel_form(channelIdx):
    if not powerGuru.localChannelsEnabled:
        return


    channel_entry = channels_list[channelIdx]
    #print("channel.sensor:", channel_entry["sensor"])
    form_data = []
    form_data.append({ "type": "hidden", "name": "idx", "access": False,"value": channelIdx})
    form_data.append({ "type": "header","subtype": "h1", "label": "Channel "+str(channelIdx+1), "access": False})
  #  form_data.append({"type": "text","required": False, "label": "code", "className": "form-control", "name": "id","access": False,  "subtype": "text","value": "ch{}".format(channelIdx+1), "disabled": True})
    form_data.append({"type": "text","required": True, "label": "name", "className": "form-control", "name": "name","access": True,  "subtype": "text","value":channel_entry["name"]})
    form_data.append({"type": "number","required": True, "label": "Load", "className": "form-control", "name": "loadW","access": True,  "description": "Max load in watts (W)","min": 0, "max": 10000,"step": 0, "value": channel_entry["loadW"]})
    form_data.append({"type": "number","required": True, "label": "GPIO", "className": "form-control", "name": "gpio","access": False,  "description": "Compoter GPIO","min": 0, "max": 37,"step": 1, "value" : channel_entry["gpio"],"disabled": True})
    
    if "lines" in channel_entry:
        if len(channel_entry["lines"])==3:
            lines = 0
        else:
            print("DEBUG:", channel_entry["lines"])
            lines = channel_entry["lines"][0]
    else:
        lines = 0    

    #form_data.append({"type": "radio-group", "required": True, "label": "Lines","inline": False, "name": "lines","access": False,"other": False, "values": [ {"label": "3-phase","value": "3phase","selected": (lines==0)} , { "label": "L1, 1-phase","value": "1","selected": (lines==1)}  , { "label": "L2, 1-phase","value": "2","selected": (lines==2)} , { "label": "L3, 1-phase","value": "3","selected": (lines==3)}]})

    form_data.append({"type": "select", "required": True, "label": "Lines","className": "form-control", "multiple": False, "name": "lines","access": False,"other": False, "values": [ {"label": "3-phase","value": "3phase","selected": (lines==0)} , { "label": "L1, 1-phase","value": "1","selected": (lines==1)}  , { "label": "L2, 1-phase","value": "2","selected": (lines==2)} , { "label": "L3, 1-phase","value": "3","selected": (lines==3)}]})


    sensor_values = []
    for sensor in sensorData.sensors:
        selected = (sensor["code"] == channel_entry.get("sensor",None))
        sensor_values.append({ "value" : sensor["code"], "label" :  "{} ({})".format(sensor["name"],sensor["code"]), "selected": selected })
    
    form_data.append({"type": "select", "required": True, "label": "Sensor",
      "className": "form-control","name": "sensor","access": False, "multiple": False,
      "values": sensor_values})

    form_data.append({ "type": "header","subtype": "h1", "label": "Targets", "access": False})

    form_data.append({ "type": "paragraph", "subtype": "p", "label": "Use this target if no exception below matches. State targets are in order and the first (1,2...) matching target will be target value for the channel. If there is no match , default the value is used.", "access": False })
 
    target_count = 0
    if "targets" in channel_entry:
        for idx,target in enumerate(channel_entry["targets"]):
            new_target_fields = ui_add_target_section(idx, target)
            form_data.extend(new_target_fields)
            target_count += 1

        
    # add one empty target to the bottom 
    new_target_fields = ui_add_target_section(target_count, {"targetStates": [], "type" : "down", "value": None})
    form_data.extend(new_target_fields)
    form_data.append({"type": "button", "subtype": "submit", "label": "Save", "className": "btn-default btn", "name": "save","access": False, "style": "default"})
    return form_data


def create_states_form(): 
    global powerGuru
    form_data = []
    form_data.append({ "type": "header","subtype": "h1", "label": "States ", "access": False})

    form_data.append({ "type": "paragraph", "subtype": "p", "label": "State code must be unique. You can add one state at time to the end. To delete a state enter \"delete\" in the formula column. Do not delete states used in channel targets.", "access": False })
 
    variableStr = ""
    for variable_code,variable in powerGuru.get_variables():
        if variable["type"] == "str":
            variableStr += "<li>{} ('{}')</li>".format(variable_code,variable["value"])
        else:
            variableStr += "<li>{} ({})</li>".format(variable_code,variable["value"])

    form_data.append({ "type": "paragraph", "subtype": "p", "label": "Currently available variables (and current value):<ul>{}</ul>".format(variableStr), "access": False })
  
    idx = 0
    for state_key, state in states.items(): 
        new_fields = ui_add_state_section(idx, state,state_key,True)
        form_data.extend(new_fields)
        idx += 1
    # empty for adding
    new_fields = ui_add_state_section(idx, {"desc":"Enter new state here","enabledIf": ""},"",False)
    form_data.extend(new_fields)

    form_data.append({"type": "button", "subtype": "submit", "label": "Save", "className": "btn-default btn", "name": "save","access": False, "style": "default"})
    return form_data


def ui_add_state_section(idx, state, state_key,existing_entry):
    fields = []
    enabledIf = state["enabledIf"]
    if existing_entry:
        code_class = "readOnly"
    else:
        code_class = ""

    fields.append({ "type": "paragraph", "className": "col-lg-12" ,"subtype": "p", "label": "<br><hr>State {}".format(idx+1), "access": False })
    fields.append({"type": "text","required": existing_entry, "label": "code", "className": "form-control code   col-lg-3 "+code_class, "name": "code_{}".format(idx),"access": True,  "subtype": "text","value":state_key})
    fields.append({"type": "text","required": existing_entry, "label": "enabled if (formula)", "className": "form-control formula   col-lg-9", "name": "enabledIf_{}".format(idx),"access": True,  "subtype": "text","value":enabledIf })
    fields.append({"type": "text","required": existing_entry, "label": "description", "className": "form-control  col-lg-12", "name" : "desc_{}".format(idx),"access": True,  "subtype": "text","value":state["desc"]}) 
    return fields


def ui_add_target_section(index, target):
    fields = []
    state_values = []
    for state_key,state in states.items(): 
        #if state.get("alwaysOn",False): 
        #    continue# do not include default state
        #channel_entry
        #if state_key in target["targetStates"]
        if "enabledIf" in state:
            state_values.append({ "value" : "state_{}".format(state_key), "label" :  "{} ({})".format(state["desc"],state_key), "selected": state_key in target["targetStates"] })
    
    print("ui_add_target_section:",target)
    
    sensorbelowSelected = (target["type"] == "sensorbelow")
    upSelected = (target["type"] == "up")
    downSelected = (target["type"] == "down")

    print("selected:",sensorbelowSelected, upSelected,downSelected)

    fields.append({"type": "paragraph", "subtype": "p", "label": "<hr>{}. Conditional target value".format(index+1), "access": False })
    fields.append({"type": "select","required": False,"description": "One or more states for this target","className": "form-control","name": "targetStates_{}".format(index),"access": False,"multiple": True,"values": state_values})
    fields.append({"type": "radio-group", "required": False, "label": "Target type","inline": False, "name": "targetType_{}".format(index),"access": False,"other": False, "values": [ {"label": "up if sensor below target","value": "sensorbelow","selected":sensorbelowSelected} , { "label": "always up","value": "up","selected": upSelected}  , { "label": "always down","value": "down","selected": downSelected} ]})
    fields.append({"type": "number","required": False, "label": "target value", "className": "form-control", "name": "target_{}".format(index),"access": False,  "description": "Target value for selected states","min": 0, "max": 100,"step": 1, "value": target.get("value",None)})
    
    return fields # thislist.extend(tropical)

async def serve_channel_editor(request):
    # https://bpmn.io/blog/posts/2021-form-js-visual-form-editing-and-embedding.html

    # testing channel editot
    #todo authetication
    # 
    idx = int(request.match_info.get('idx', "-1"))
    channelIdx = idx # int(request.match_info.get('idx', "-1")) # int(request.rel_url.query['idx']) # 0-indexed
    with open("www/channel.html", 'r', encoding='utf8') as f:
        text_out = f.read()

    formData_str = json.dumps(create_channel_form(channelIdx), indent=None, separators=(",",":"))
    text_out = text_out.replace("#formData#", formData_str)
    return Response(text=text_out, content_type='text/html');
  
async def serve_states_editor(request):
    #todo authetication
    with open("www/states.html", 'r', encoding='utf8') as f:
        text_out = f.read()

    formData_str = json.dumps(create_states_form(), indent=None, separators=(",",":"))
    text_out = text_out.replace("#formData#", formData_str)
    return Response(text=text_out, content_type='text/html');
  

def list_objects_to_dict(list_in, key_name = 'name', value_name = 'value',end_regex = '_\d+$'):
    out_dict = {}
    for li in list_in:
        if key_name in li and value_name in li:
            key = li[key_name].replace("[]","")

            if end_regex: # try to find index from the end, default end variable_name_1
                m = re.search(end_regex, key)
            else:
                m = None
            if m:
                dict_idx =m.group()[1:]
                key_start = key[:m.span()[0]]  
                print("dict_key:",dict_idx, ", key_start:", key_start)
            else:
                key_start = key
                dict_idx = None
                 
            value = li[value_name]
            if dict_idx:
                if key_start not in out_dict:
                    out_dict[key_start] = {} #empty dictionary
                if dict_idx in out_dict[key_start]:
                    if not isinstance(out_dict[key_start][dict_idx], list):
                        out_dict[key_start][dict_idx] = [out_dict[key_start][dict_idx]] # new_array ##
                    out_dict[key_start][dict_idx].append(value) ##
                else:
                    out_dict[key_start][dict_idx] = value ##
            else:
                if key in out_dict:
                    if not isinstance(out_dict[key], list):
                        out_dict[key] = [out_dict[key]] # new_array ##
                    out_dict[key].append(value) ##
                else:
                    out_dict[key] = value ##

    return out_dict


async def save_editor(request):
    obj = await request.json()
    #print("save_editor")
    pp.pprint(obj)
    if obj["type"] ==  "states":
        channel_input = list_objects_to_dict(obj["data"])
        print("channel_input")
        pp.pprint(channel_input)
        

        # get max idx to handle
        max_idx = -1
        for key,enabledIf in channel_input["enabledIf"].items():
            if enabledIf:
                max_idx = max(max_idx,int(key))
        for key,code in channel_input["code"].items():
            if code:
                max_idx = max(max_idx,int(key))
        #for key,desc in channel_input["desc"].items():
        #    max_idx = max(max_idx,int(key))

        print("max_idx:",max_idx)
        states_new = {}
        for idx in range(max_idx+1):
            new_state = {}
            new_state["enabledIf"] = channel_input["enabledIf"][str(idx)]
            new_state["desc"] = channel_input["desc"][str(idx)]
            if new_state["enabledIf"] != "delete":
                states_new[channel_input["code"][str(idx)]] = new_state
        pp.pprint(states_new)
        print("saving...")
        save_data_json(states_new,s.states_filename)

    elif obj["type"] ==  "channel":
        channel_input = list_objects_to_dict(obj["data"])
        
        print("channel_input")
        pp.pprint(channel_input)
        idx = int(channel_input["idx"])
        channel = channels_list[idx]
        channel["name"] = channel_input["name"]
        channel["loadW"] = int(channel_input["loadW"])
        line_mapping = {"3phase":[1,2,3],"1": [1],"2": [2],"3": [3]}
        channel["lines"] = line_mapping[channel_input["lines"]]
        channel["sensor"] = channel_input["sensor"]
        targets_new = []
        
        target_range = range(min(len(channel_input["target"]),len(channel_input["targetStates"])))
        for i in target_range:
            targetIdx = str(i)
            if  not isinstance(channel_input["targetStates"][targetIdx], list):
                channel_input["targetStates"][targetIdx] = [channel_input["targetStates"][targetIdx]]    
            
            if targetIdx in channel_input["targetStates"]:  # tähän vielä type?
                targetType = channel_input["targetType"][targetIdx]
                targetValue = None 
                if targetType== "sensorbelow":
                    if targetIdx in channel_input["target"]:
                        targetValue = channel_input["target"][targetIdx] 
                        upIf = "{}<{}".format(channel_input["sensor"],targetValue)
                    else:
                        continue #undefined value
                elif targetType== "up":
                    upIf = "True"
                elif targetType== "down":
                    upIf = "False"

                states_cleaned = []
                for state in channel_input["targetStates"][targetIdx]:
                    states_cleaned.append(state.replace("state_","")  )

                targets_new.append({"targetStates" : states_cleaned,"upIf" : upIf, "type" : targetType, "value": targetValue})
        channel["targets"] = targets_new 

        #pp.pprint(channel_input)
        #print("=========>")
        #pp.pprint(channel)

    
        # replace channel enty
        for n, i in enumerate(channels_list):
            if n == idx:
                channels_list[n] = channel
        #pp.pprint(channels_list)
        #nyt save, johonkin reload/restart
        save_data_json(channels_list,s.channels_filename)
        print("##Z2")
    
    print("##end of save_editor")
    return web.Response(text=f"Thanks for your contibution!")

async def serve_status(request):
    global powerGuru
    async with sse_response(request) as resp:
        while True:
            #data = 'Server Time : {}'.format(datetime.now())
            status_obj = powerGuru.get_status(True)
            
            #print(data)
            #voisiko viimeisin update mennä globaaliin, jota tutkitaan vaikka sekunnin välein, jos uutta niin tulostetaan json
            await resp.send(json.dumps(status_obj))  
            while powerGuru.status_propagated:  
                await asyncio.sleep(1)
    return resp
#def get_request_array():

async def serve_states(request):
    states_requested = get_requested_states(request)

    states = {"states": [], "ts" : time.time()}
    if current_states:
        for state in current_states:
            if states_requested is None or state in states_requested:
                #print(state, " is in states_requested:", states_requested)
                states["states"].append(state)
            #else:
            #    print(state, " is not in states_requested:", states_requested)
    return Response(text=json.dumps(states), content_type='application/json')

def get_requested_states(request):
    if not 'states' in request.rel_url.query:
        print("Missing parameter: states")
        #return Response(text="Missing parameter: states", content_type='text/html')
        return None
    else:
        states_requested_str = request.rel_url.query['states']

    #print("states_requested_str:", states_requested_str)
    states_requested = states_requested_str.split(",")
    #print("states_requested:", states_requested)

    for idx, state in enumerate(states_requested):
        if state.strip().isdigit():
            states_requested[idx] = int(state.strip())
    return states_requested
  

async def serve_state_series(request):
    global powerGuru
    #TODO: cache in the future
    #TODO: parameters, e.g.price area, bcdc location, kai...?
    #TODO: limit queries, eg. 4 for ip-address/24h if no API-key, with API key more but not unlimited

    states_requested = get_requested_states(request)
    if not 'price_area' in request.rel_url.query:
        return Response(text="Missing parameter: price_area", content_type='text/html')

    #TODO: nämä parametreista
    start = powerGuru.get_current_period_start()
    end = start +3600*24

    # user can limit the time window, in future cached version there could be cache filters
    if 'start' in request.rel_url.query:
        start = max(start,int(request.rel_url.query['start']))
    if 'end' in request.rel_url.query:
        end = min(end,int(request.rel_url.query['end']))

    #One instance supports only one price area
    price_area = request.rel_url.query['price_area']
    if price_area != powerGuru.get_setting("SpotPriceArea"):
        return Response(text="Only price_area {} is supported by this server.".format(powerGuru.get_setting("SpotPriceArea")), content_type='text/html')


    #first create time series for variables (excluding internal)

  
    aggregate_dayahead_prices_timeser(start,end)
    aggregate_solar_forecast_timeser(start,end)

    # this populates states timeseries
    check_states_timeser(start,end)

    state_series = powerGuru.get_values_timeser("states",start,end,states_requested)
    state_series["ts"] = time.time()

    return Response(text=json.dumps(state_series), content_type='application/json')
    


async def serve_dashboard(request):
    session = await get_session(request)
    session['last_visit'] = time.time()
    # see also: http://demos.aiohttp.org/en/latest/tutorial.html#static-files
    with open("www/dashboard.html", 'r', encoding='utf8') as f:
              #  body= bytes(f.read(), "utf-8")
        return Response(text=f.read(), content_type='text/html');

async def serve_admin(request):
    # see also: http://demos.aiohttp.org/en/latest/tutorial.html#static-files
    with open("www/dashboard.html", 'r', encoding='utf8') as f:
              #  body= bytes(f.read(), "utf-8")
        return Response(text=f.read(), content_type='text/html');



#async def add_user(request: web.Request) -> web.Response:
async def process_telegraf_post(request):
    global gridenergy_data, dayahead_list, forecastpv_list
    global powerGuru

    obj = await request.json()
    #pp.pprint(obj)

    #TODO: different metrics could be parametrized, so addional metrics (eg. PV inverter data) could be added without code changes
    if "metrics" in obj:
        gridenergy_new = filtered_fields(obj["metrics"],"gridenergy",False)
        #this
        if len(gridenergy_new)==1: # there should be only one entry

            gridenergy_data = gridenergy_new[0]
            #TODO: trigger recalculate also after other updates but wait thats all requests in the incoming Telegraf buffer are processed
            powerGuru.recalculate()
        
        temperature_new = filtered_fields(obj["metrics"],"temperature",False)
        if len(temperature_new)>0:
            temperature_data = temperature_new
            process_sensor_data(temperature_data)
            
        dayahead_new = filtered_fields(obj["metrics"],"dayahead",False,s.dayahead_file_name)
        if len(dayahead_new)>0:
            dayahead_list = dayahead_new
            aggregate_dayahead_prices()

        forecastpv_new = filtered_fields(obj["metrics"],"forecastpv",False,s.forecastpv_file_name)
        if len(forecastpv_new)>0:
            forecastpv_list = forecastpv_new
            aggregate_solar_forecast()

    return web.Response(text=f"Thanks for your contibution Telegraf!")

       

def run_telegraf_once(cmd = "telegraf -once --config-directory /etc/telegraf/telegraf.d", start_delay = 10): 
    time.sleep(start_delay) # let the main thread start
    cmd_arr = cmd.split()
    FNULL = open(os.devnull, 'w') # or  stdout=subprocess.PIPE  or FNULL =open("/tmp/ffmpeg.log", "a+")
    telegrafProcess = subprocess.Popen(cmd_arr, shell=False,stdout=FNULL, stderr=subprocess.STDOUT)
     
    
        
def main(argv): 
    load_program_config()    
 
    signal.signal(signal.SIGINT, sig_handler)
    
    # Run Telegraf once to get up-to-date data
    run_telegraf_once_thread =  Thread(target=run_telegraf_once)
    run_telegraf_once_thread.start()

    #aiohttp
    #app = web.Application()
    FernetKey = '6ip63k7p0jh5rR/2Bs4AdSM35FMQWovGwSz0tydU6ro='
    #middleware = session_middleware(SimpleCookieStorage())
    middleware = session_middleware(EncryptedCookieStorage(FernetKey))

    app = web.Application(middlewares=[middleware])
    app.router.add_route('GET', '/', serve_dashboard)
    app.router.add_route('GET', '/status', serve_status)
    app.router.add_route('GET', '/states', serve_states)
    app.router.add_route('GET', '/state_series', serve_state_series)
    
    app.router.add_route('POST', '/telegraf', process_telegraf_post)
    app.router.add_route('GET', '/admin', serve_admin)
   

   # app.router.add_route('GET', '/(channels\/\dd*|states)', serve_editor) 

    app.router.add_route('GET', '/channel/{idx}', serve_channel_editor) 
    app.router.add_route('GET', '/states', serve_states_editor) 
    
    app.router.add_route("POST", '/editor', save_editor)

    

    # https://github.com/bugov/aiohttp-basicauth-middleware
    """
    app.middlewares.append(
    basic_auth_middleware(
        ('/states',),
        {'user': 'password'},
    )
    )
    """
    

    app.middlewares.append(
    basic_auth_middleware(
        ('/states','/channel/','/editor/'),
        {'powerguru': 'bceeffe128eb5f0f76a7c9f7c3d93fededa859f0f1689e00ff7bff4b93c7ed97206d2844a2e3327fc14edc9e36ce4601a5409bb1a34bda332715acb24b5cbc5e'},
        lambda x: hashlib.sha512(bytes(x, encoding='utf-8')).hexdigest(),
    )
    )
    
    #generate digest manually: echo -n 'my_new_password'|openssl dgst -sha512


    #channel\/\d*

    web.run_app(app, host='0.0.0.0', port=8080)

    #TODO: this could be main loop where recalculation are started after new data arrived from Telegraf
    while True:
        pass
    


if __name__ == "__main__":
    main(sys.argv[1:])
    

