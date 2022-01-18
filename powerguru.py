#!/usr/bin/env python
# coding: utf-8 
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
from datetime import datetime

import socket

from threading import Thread, current_thread
import RPi.GPIO as GPIO # handle Rpi GPIOs for connected to relays

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS




GPIO.setwarnings(False)
#use GPIO-numbers to refer GPIO pins
GPIO.setmode(GPIO.BCM)


import settings as s #settings file

import pprint
pp = pprint.PrettyPrinter(indent=4)


data_updates = {}
gridenergy_data = None
temperature_data = None
dayahead_list = None 
forecastpv_list = None
current_conditions = None

netPreviousTotalEnergyPeriod = -999
netPreviousTotalEnergy = -1
purchasedEnergyPeriodNet = 0 
netPeriodMeasurementCount = 0

sensor_settings = None
conditions = None
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
        

        self.lines = [ (1, 0),(2, 0),(3, 0)]
        
        self.lines_sorted = self.lines
        self.status_propagated = True
        self.variables = {}

    def set_variable(self,field_code,value):
        self.variables[field_code] = {"value": value, "ts" : time.time(), "type" : "num"}

    def print_variables(self):
        print("PowerGuru.variables()")
        for vkey,variable in self.variables.items():
            print("{}={}".format(vkey,variable["value"]))

    
    def set_variables(self,new_values):
        field_group = new_values["name"]
        for vkey,value in new_values["fields"].items():
            vcode = "{}:{}".format(field_group,vkey)
            self.set_variable(vcode,value)
        
        #print("*******set_variables********")
        #pp.pprint(self.variables)
        
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
        
        status = {"channels": [], "updates":[], "sensors":[], "variables":[], "current_conditions":None}

        for channel in channels:
            status["channels"].append({ "code" : channel.code, "name" : channel.name, "up":  channel.up, "target" : channel.target })
        
        for variable_code,variable in powerGuru.get_variables():
            status["variables"].append({ "code" : variable_code, "value" : variable["value"], "ts":  variable["ts"], "type" : variable["type"] })


        for update_key, update_values in data_updates.items():
            updated_dt = (tz_utc.localize(datetime.utcnow())-update_values["updated"])
            updated_dt = updated_dt - timedelta(microseconds=updated_dt.microseconds) #round
            
            latest_ts_str = datetime.fromtimestamp(update_values["latest_ts"]).strftime("%Y-%m-%dT%H:%M:%S%z") 
            status["updates"].append({ "code" : update_key, "updated" : update_values["updated"].strftime("%Y-%m-%dT%H:%M:%S%z") , "latest_ts":  latest_ts_str })
                
        for sensor in sensorData.sensors:
            status["sensors"].append({ "code" : sensor["code"], "id" : sensor["id"], "name" : sensor["name"], "value":  sensor["value"] })

        if current_conditions:
            status["current_conditions"] = current_conditions

     

        if gridenergy_data:
            status["Wsys"] = gridenergy_data["fields"]["Wsys"]
        else:
            status["Wsys"] = None
        
        return status


    # this is the main calculation function    
    def recalculate(self):
        print ('#recalculate')
        #global self
        global purchasedEnergyPeriodNet, netPreviousTotalEnergy, netPreviousTotalEnergyPeriod,netPeriodMeasurementCount
        global current_conditions
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
            
        currentNettingPeriod = int(time.time()/(self.nettingPeriodMinutes*60))

        if netPreviousTotalEnergyPeriod != currentNettingPeriod:
            # this should probably be run when a new hour (period) starts, not always
            aggregate_dayahead_prices()

            netPreviousTotalEnergyPeriod =  currentNettingPeriod
            netPeriodMeasurementCount = 0 
    #TODO: tsekkaa miksi purchasedEnergyPeriodNet nollaantuu viivellä periodin vaihtuessa
        
        purchasedEnergyPeriodNet = cumulativeEnergy-netPreviousTotalEnergy
        netPeriodMeasurementCount += 1
        if netPeriodMeasurementCount == 1:
            netPreviousTotalEnergy = cumulativeEnergy
        self.set_variable("purchasedEnergyPeriodNet" , round(purchasedEnergyPeriodNet,2))
        print(" {} cumulativeEnergy- {} netPreviousTotalEnergy = {} purchasedEnergyPeriodNet ".format(cumulativeEnergy,netPreviousTotalEnergy,purchasedEnergyPeriodNet))
        
        #TODO: OVERLOAD CONTROL!!!    
        self.setLoad(loadsA[0],loadsA[1],loadsA[2])             
    
        current_conditions = check_conditions()

        #TODO:miksi eri loopit, randomin takia?, vai jäänne
        for channel in channels:
            target = channel.getTarget(current_conditions)
            #print(channel.name, " got target: ",target)
        
        random_channels = channels.copy()
        random.seed()
        random.shuffle(random_channels) # set up load in random order
        
        for channel in random_channels:
            target = channel.getTarget(current_conditions)  
            channels[channel.idx].target = target 
            if target["keep_up"]:
                #channel.on = True
                loadChange = channel.loadUp() #
                if abs(loadChange) > 0: #only 1 v´chnage at one time, eli ei liikaa muutosta minuutissa
                    break
            elif not target["keep_up"] and target["condition"]: 
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
                # set sensor value to variables, so it can be used in conditions
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
                tn = {"condition" : target["condition"], "sensor" : target.get("sensor",None), "upIf": target.get("upIf",None),"valueabove": target.get("valueabove",None), "valuebelow": target.get("valuebelow",None), "forceOn" :  target.get("forceOn",None)}
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
    
    
    def getTarget(self,current_conditions):
        # get first channel target where condition is matching
        for target in self.targets:
            if target["condition"] in current_conditions:
                #print("target condition is in current conditions",target["condition"])
                # uusi versio tulossa tähän
                # yksinkertaista iffittelyä lopullisessa
                
                if "upIf" in target and target["upIf"] is not None:
                    keep_up,error_in_test = test_formula( target["upIf"],self.name+ ":"  +target["condition"]  )  
                    if error_in_test: #possibly error in target t, try next one (should we panic and break )
                        #TODO: error in formula (e.g. wrong variable) should be reported somehow - error list...
                        continue # try next target
                    else: #found first matching target
                        return {"condition" : target["condition"],"keep_up":keep_up,"upIf": target["upIf"] }    

        
        return {"condition" : None,"keep_up":False} # no matching target
    
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
    
    
def check_conditions():
    ok_conditions = []
    global conditions
    global powerGuru
  
    #TODO: spotlowesthours - kuluvan päivän x halvinta tuntia, tässä pitäisi kyllä ottaa myös kuluneet
    #voisi ottaa ko päivän kuluneet ja koko tiedetyn tulevaisuuden
    for condition_key,condition in conditions.items(): # check 
        if "enabledIf" in condition:
            condition_returned, error_in_test = test_formula( condition["enabledIf"],condition_key)  
            if condition_returned and not error_in_test: 
                ok_conditions.append(condition_key)      

    for condition_key,condition in conditions.items(): 
        conditions[condition_key]["enabled"] = (condition_key in ok_conditions)
        
    pp.pprint (ok_conditions)
    return ok_conditions


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


        
def reportState(price_fields): 
    global powerGuru
    condition_fields = {}
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
           
        for channel in channels:
            channel_fields[channel.code]=  (1 if channel.up else 0)
        json_body.append( {
        "measurement": "channels",
        "time":  datetime.now(timezone.utc),
        "fields": channel_fields
        })

        for condition_key,condition in conditions.items(): 
            condition_fields[condition_key]=  (1 if condition["enabled"] else 0)
            
        json_body.append( {
            "measurement": "conditions",
            "time":  datetime.now(timezone.utc),
            "fields": condition_fields
            })

        write_api = ifclient.write_api(write_options=SYNCHRONOUS)
        write_api.write("", "", json_body)

       # print ("Wrote to influx")
    except:
         print ("Cannot write to influx", sys.exc_info())
         
 

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





def load_program_config():
    global actuators,sensorData,thermometers, powerGuru
    global sensor_settings,conditions #,switches
    global dayahead_list, forecastpv_list
    global channels_list
    
    powerGuru = PowerGuru(s.powerguru_file_name) 
    #TODO: read cached forecast and price info and check validity?

     #1-wire
    sensor_settings = s.read_settings(s.sensor_settings_filename)  
    sensorData = SensorData(sensor_settings["sensors"])



    #channels_list
    channels_list = s.read_settings(s.channels_filename) 
    idx = 0
    for channel in channels_list:
        channel =  Channel(idx,"ch"+str(idx+1),channel)
        channels.append(channel)
         
        idx += 1

    # conditions
    conditions = s.read_settings(s.conditions_filename) 

    
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
#async def now_new_data():
#    return 42

async def status(request):
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


async def index(request):
    # see also: http://demos.aiohttp.org/en/latest/tutorial.html#static-files
    with open("www/index.html", 'r', encoding='utf8') as f:
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
            #
            #powerGuru.set_variables(gridenergy_new[0])
            #powerGuru.print_variables() #debugging
            gridenergy_data = gridenergy_new[0]
            #TODO: trigger recalculate also after other updates but wait thats all requests in the incoming Telegraf buffer are processed
            powerGuru.recalculate()
        
        temperature_new = filtered_fields(obj["metrics"],"temperature",False)
        if len(temperature_new)>0:
            #powerGuru.set_variables(temperature_new)
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
    app = web.Application()
    app.router.add_route('GET', '/index.html', index)
    app.router.add_route('GET', '/status', status)
    app.router.add_route('POST', '/telegraf', process_telegraf_post)

   
    web.run_app(app, host='0.0.0.0', port=8080)

    #TODO: this could be main loop where recalculation are started after new data arrived from Telegraf
    while True:
        pass
    


if __name__ == "__main__":
    main(sys.argv[1:])
    

