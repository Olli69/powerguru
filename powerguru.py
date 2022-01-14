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

from threading import Thread, current_thread


import RPi.GPIO as GPIO # handle Rpi GPIOs for connected to relays

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS


# via Telegraf relay to influxDB
ifclient = InfluxDBClient(url = "http://127.0.0.1:8086",token="")

GPIO.setwarnings(False)
#use GPIO-numbers to refer GPIO pins
GPIO.setmode(GPIO.BCM)

solarForecastBlocks = {"6" : 0, "12" : 0, "18" : 0, "24" : 0} 


import settings as s #settings file

import pprint
pp = pprint.PrettyPrinter(indent=4)

tz_local = pytz.timezone(s.timeZoneLocal)
tz_utc = pytz.timezone("UTC")

data_updates = {}
gridenergy_data = None
temperature_data = None
dayahead_list = None 
forecastpv_list = None
current_conditions = None
"""
previousTotalEnergyHour = -999
previousTotalEnergy = -1
hourCumulativeEnergyPurchase = 0
hourMeasurementCount = 0
"""
#new version of ...
netPreviousTotalEnergyPeriod = -999
netPreviousTotalEnergy = -1
purchasedEnergyPeriodNet = 0 
netPeriodMeasurementCount = 0


sensor_settings = None
#switches = None
conditions = None
channels_list = None

# global variables
channels = []
sensorData = None
powerSystem = None
pricesAndForecast = None



# get current prices and expected future solar, e.g. solar6h is solar within next 6 hours
def getPriceAndForecast():
    global dayahead_list, forecastpv_list
    global powerSystem
    
    dtnow = datetime.now()
    now_local = dtnow.astimezone(tz_local).isoformat()
    local_time = now_local[11:19]
    """
    if s.daytimeStarts < local_time < s.daytimeEnds:
        transferPrice = s.transferPriceDay
        energyPrice = s.energyPriceDay
    else:
        transferPrice = s.transferPriceNight
        energyPrice = s.energyPriceNight
            
    totalPrice = transferPrice+s.electricityTax+energyPrice
    """
    
    energyPriceSpot = None
    if dayahead_list is not None:
        for price_entry in dayahead_list:
            if price_entry["timestamp"] < time.time() and price_entry["timestamp"] > time.time()-3600:
                energyPriceSpot = price_entry["fields"]["energyPriceSpot"]


    for sfbCode,sfb in solarForecastBlocks.items():
        solarForecastBlocks[sfbCode] = 0
    #print("ennen solarForecastBlocks", solarForecastBlocks)
    
    if forecastpv_list is not None:
        for fcst_entry in forecastpv_list:
            for sfbCode,sfb in solarForecastBlocks.items():
                futureHours = int(sfbCode)        
                if fcst_entry["timestamp"] < time.time()+(futureHours*3600):
                    solarForecastBlocks[sfbCode] += fcst_entry["fields"]["pvrefvalue"]


    powerSystem.set_variable("energyPriceSpot" , round(energyPriceSpot,3))
    return_value =  { "energyPriceSpot" : energyPriceSpot}
   
    for sfbCode,sfb in solarForecastBlocks.items():  
        blockCode = "solar{}h".format(sfbCode)
        return_value[blockCode] = sfb
        powerSystem.set_variable(blockCode , sfb)
    
    return return_value



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
class PowerSystem:
    def __init__(self):
        self.lines = [ (1, 0),(2, 0),(3, 0)]
        self.lines_sorted = self.lines
        self.status_propagated = True
        self.variables = {}

    def set_variable(self,field_code,value):
        self.variables[field_code] = {"value": value, "ts" : time.time(), "type" : "num"}

    def print_variables(self):
        print("PowerSystem.variables()")
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
            
            projectedOverload = line[1]-s.basicInfo["maxLoadPerPhaseA"]+requested_phase_current
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
            overLoad = line[1]-s.basicInfo["maxLoadPerPhaseA"]
            if overLoad<0:
                print("No overload in line ", line,", overload:" ,overLoad)
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
            available_lines.append({"l" : line[0],"availableA":s.basicInfo["maxLoadPerPhaseA"]-line[1]})
        return available_lines #näitä voisi kuormittaa jos ei ole jo kuormitettu

    #for the dashboard
    def get_status(self,set_status_propagated):
        if set_status_propagated:
            self.status_propagated = True  
        
        status = {"channels": [], "updates":[], "sensors":[], "variables":[], "current_conditions":None}

        for channel in channels:
            status["channels"].append({ "code" : channel.code, "name" : channel.name, "up":  channel.up, "target" : channel.target })
        
        for variable_code,variable in powerSystem.get_variables():
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

        if pricesAndForecast is not None:
            status["energyPriceSpot"] = pricesAndForecast.get("energyPriceSpot",None)
        else:
            status["energyPriceSpot"] = None
 

        if gridenergy_data:
            status["Wsys"] = gridenergy_data["fields"]["Wsys"]
        else:
            status["Wsys"] = None
        
        return status
                       


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
        global powerSystem
        for sensor in self.sensors:
            if sensor["id"] == id:
                sensor["value"]= value
                # set sensor value to variables, so it can be used in conditions
                powerSystem.set_variable(sensor["code"],round(value,1))
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
        
        self.loadW =  data.get("loadW",0)
        self.up = False
        self.reverse_output = data.get("reverse_output",False) #esim. lattialämmityksen poissa-kytkin, todo gpio-handleen
        self.target = None

        lines = []  
        
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
                tn = {"condition" : target["condition"], "sensor" : target.get("sensor",None), "reachedWhen": target.get("reachedWhen",None),"valueabove": target.get("valueabove",None), "valuebelow": target.get("valuebelow",None), "forceOn" :  target.get("forceOn",None)}
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
                
                if "reachedWhen" in target and target["reachedWhen"] is not None:
                    target_reached,error_in_test = test_formula( target["reachedWhen"],self.name+ ":"  +target["condition"]  )  
                    if error_in_test: #possibly error in target t, try next one (should we panic and break )
                        #TODO: error in formula (e.g. wrong variable) should be reported somehow - error list...
                        continue # try next target
                    else: #found first matching target
                        # käytetään  reached, condition 
                        return {"condition" : target["condition"],"reached":target_reached,"reachedWhen": target["reachedWhen"] }    

        
        return {"condition" : None,"reached":True} # no matching target
    
    def getLine(self,l):
        for line in self.lines:
            if line["l"] == l:
                return line
        return None
    
    def loadUp(self):
        global powerSystem
        print("loadUp", self.name)
        if powerSystem.requestCapacity(self.lines):
            print("requestCapacity ok")
            setOutGPIO(self.gpio,True)
            self.up = True
        else:
            print("requestCapacity failed")
        
       
        
        """
        lineResources = powerSystem.getLineCapacity(reverse=False)
        
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
        lineResources = powerSystem.getLineCapacity(reverse=True) #katso saisiko ton amppeerimäärän laitteelta
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
    global powerSystem
  
    #TODO: spotlowesthours - kuluvan päivän x halvinta tuntia, tässä pitäisi kyllä ottaa myös kuluneet
    #voisi ottaa ko päivän kuluneet ja koko tiedetyn tulevaisuuden
    for condition_key,condition in conditions.items(): # check 
        if "c" in condition:
            condition_returned, error_in_test = test_formula( condition["c"],condition_key)  
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
    for vkey,v in powerSystem.get_variables():
        if vkey in eval_string:
            variable_value = powerSystem.get_value(vkey,None)
            if variable_value is not None:
                eval_string = eval_string.replace(vkey,str(variable_value))
            else:
                print("Variable {} value was None:".format(vkey))
                return False, True
            
    try:
        eval_value = eval(eval_string,{})    
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception( exc_type,exc_value, exc_traceback,limit=5, file=sys.stdout)
        print("eval_string: ",eval_string)
        return False, True  

    #print("formula {},  [{}] => {}".format(info,eval_string, eval_value))
    return eval_value, False 



def readSettings(settings_filename=None):
    global machineSettings
    
    if settings_filename is None:
        isMachineSettings = True
        settings_filename = "settings/{}.json".format(socket.gethostname())
    else:
        isMachineSettings = False
        
    print(settings_filename)
    if os.path.exists(settings_filename):
        f = open(settings_filename)
        ls = json.load(f)
        f.close()
    else:      
        ls = json.loads("{}") 
        
    if isMachineSettings:     
        machineSettings = ls
    return ls
        

        

        
def reportState(price_fields): 
    temperature_fields = {}
    state = {}
    condition_fields = {}
    channel_fields = {}
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
         


# this is the main function called by Reactor event handler and defined in task.LoopingCall(doWork)    
def recalculate():
    print ('#recalculate')
    global powerSystem, pricesAndForecast
    # old...
    #global previousTotalEnergyHour, previousTotalEnergy,hourCumulativeEnergyPurchase, hourMeasurementCount
    global purchasedEnergyPeriodNet, netPreviousTotalEnergy, netPreviousTotalEnergyPeriod,netPeriodMeasurementCount
    global solarForecastBlocks
    global current_conditions
    
    
    global gridenergy_data, temperature_data, dayahead_list, forecastpv_list
  
    #todo: check data age
    if gridenergy_data is None or "fields" not in gridenergy_data:
        print("No gridenergy_data")
        return False
    
    # TODO: read from cache , check validity (in init) , handle cases if not used
    #if dayahead_list is None or forecastpv_list is None:
    #    return False
    
    importTot = 0
    imports = [0,0,0]
    price_fields = {}
    loadsA = [0,0,0]
    
    # Go through all connected thermometers
    
    dtnow = datetime.now()
    now_local = dtnow.astimezone(tz_local).isoformat()
    
    pricesAndForecast = getPriceAndForecast()
    #print("pricesAndForecast",pricesAndForecast)
        
        
    loadsA[0] = gridenergy_data["fields"]["AL1"]
    loadsA[1] = gridenergy_data["fields"]["AL2"]
    loadsA[2] = gridenergy_data["fields"]["AL3"]
    imports[0] = gridenergy_data["fields"]["WL1"]
    imports[1] = gridenergy_data["fields"]["WL2"]
    imports[2] = gridenergy_data["fields"]["WL3"]
    importTot = gridenergy_data["fields"]["Wsys"]
    cumulativeEnergy = gridenergy_data["fields"]["kWhTOT"]
    
    
    price_fields[ "sale"]= (-importTot if importTot<0 else 0.0)
    price_fields[ "purchase"]= (importTot if importTot>0 else 0.0)
 


    # sales only for negative import
    price_fields[ "sale"]= (-importTot if importTot<0 else 0.0)
    price_fields[ "purchase"]= (importTot if importTot>0 else 0.0)
        
    # yösähkö erikseen, tää olisi hyvä parametroida
    local_time = now_local[11:19] 
    #TODO nämä parametreistä
    if "07:00:00" < local_time < "22:00:00":# and dtnow.isoweekday()!=7: 
        price_fields[ "purchaseDay"]= (importTot if importTot>0 else 0.0)
        price_fields[ "purchaseNight"]= 0.0
    else:
        price_fields[ "purchaseNight"]= (importTot if importTot>0 else 0.0)
        price_fields[ "purchaseDay"]= 0.0
    
 
  
    # new, todo: tähän tallennukset influxiin
    if s.nettingPeriodMinutes!= 0:
        if netPreviousTotalEnergy == -1:
            netPreviousTotalEnergy = cumulativeEnergy
        currentNettingPeriod = int(time.time()/(s.nettingPeriodMinutes*60))
        if netPreviousTotalEnergyPeriod != currentNettingPeriod:
            netPreviousTotalEnergyPeriod =  currentNettingPeriod
            netPeriodMeasurementCount = 0 
        purchasedEnergyPeriodNet = cumulativeEnergy-netPreviousTotalEnergy
        netPeriodMeasurementCount += 1
        if netPeriodMeasurementCount == 1:
            netPreviousTotalEnergy = cumulativeEnergy
        powerSystem.set_variable("purchasedEnergyPeriodNet" , purchasedEnergyPeriodNet)
        print(" {} cumulativeEnergy- {} netPreviousTotalEnergy = {} purchasedEnergyPeriodNet ".format(cumulativeEnergy,netPreviousTotalEnergy,purchasedEnergyPeriodNet))


        #print("purchasedEnergyPeriodNet",purchasedEnergyPeriodNet,cumulativeEnergy,netPreviousTotalEnergy)

    """
    #Old
    if previousTotalEnergy == -1: #first measurement after init
        previousTotalEnergy = cumulativeEnergy
    if previousTotalEnergyHour != dtnow.hour-1: #first measurement within hour
        # TODO: could get exact number from the DB
        previousTotalEnergyHour = dtnow.hour-1
        hourMeasurementCount = 0
    hourCumulativeEnergyPurchase = cumulativeEnergy-previousTotalEnergy  
    #TODO: nämä pois kun uusi todettu toimivaksi
    print("hourCumulativeEnergyPurchase",hourCumulativeEnergyPurchase,cumulativeEnergy,previousTotalEnergy)
    price_fields["hourCumulativeEnergyPurchase"]= hourCumulativeEnergyPurchase               
    hourMeasurementCount +=1
    if hourMeasurementCount==1: #first measurement of hour, init cumulative
        previousTotalEnergy = cumulativeEnergy
    """  
      
    #TODO: OVERLOAD CONTROL!!!    
    powerSystem.setLoad(loadsA[0],loadsA[1],loadsA[2])             
 
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
        #print ("recalculate", channel.code,"target:",target)  
        if not target["reached"]:
            #channel.on = True
            loadChange = channel.loadUp() #
            if abs(loadChange) > 0: #only 1 v´chnage at one time, eli ei liikaa muutosta minuutissa
                break

        elif target["reached"] and target["condition"]: 
            #print("Channel {:s} ,condition {:s}, target reached ".format(channel.code,target["condition"]))
            loadChange = channel.loadDown()
            #channel.on = False
            if abs(loadChange) > 0:
               # print ("loadDown loadChange:", loadChange)
                break
  

    powerSystem.set_status_unpropagated()
    # export to influxDB
    #TODO: write current_conditions etc calculated  - price_fields - fields to influx
    reportState(price_fields)




def load_program_config(signum=None, frame=None):
    global actuators,sensorData,thermometers, powerSystem
    global sensor_settings,conditions #,switches
    global dayahead_list, forecastpv_list
    global channels_list
    
    #TODO: read cached foracast and price info and check validity

     #1-wire
    sensor_settings = readSettings(s.sensor_settings_filename)  
    sensorData = SensorData(sensor_settings["sensors"])

    #switches
    #switches = readSettings(switches_settings_filename) 

    #channels_list
    channels_list = readSettings(s.channels_filename) 
    idx = 0
    for channel in channels_list:
        channel =  Channel(idx,"ch"+str(idx+1),channel)
        channels.append(channel)
         
        idx += 1

    # conditions
    conditions = readSettings(s.conditions_filename) 

 
    #print(sensor_settings)
    #pp.pprint(sensorData.sensors)  
    
    powerSystem = PowerSystem()    
    
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
""" 
     
async def process_ws_msg(websocket, path):
    print("***************",path)

    global gridenergy_data, dayahead_list, forecastpv_list


    #try:
    msg = "[]"
    while True:
        try: 
            msg = "[]"
            msg = await websocket.recv()
    
        #msg = await websocket.recv()
        #except:
        #    print('Reconnecting')
        #    websocket = await websocket.connect(ws_url)
        except IncompleteReadError:
            print("IncompleteReadError")
            pass
        
        except ConnectionClosedError: 
            pass
            #if msg is not None:
            #    print("Connection closed, but we have a message with length {}.".format(len(msg))) 
            #else:
            #    print("Connection closed and we have no msg.") 
              
        except:
            if msg is not None:
                print("Exception, but we have a message with length {}.".format(len(msg))) 
            else:
                print("Exception and we have no msg.")
                 
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_exception( exc_type,exc_value, exc_traceback,limit=5, file=sys.stdout)
   
            
        if msg is not None:           
            obj = json.loads(msg)      
            if "metrics" in obj:
                gridenergy_new = filtered_fields(obj["metrics"],"gridenergy",True)
                if len(gridenergy_new)==1: # there should be only one entry
                    gridenergy_data = gridenergy_new[0]
                    recalculate()
                
                
                dayahead_new = filtered_fields(obj["metrics"],"dayahead",True,s.dayahead_file_name)
                if len(dayahead_new)>0:
                    dayahead_list = dayahead_new
                    

                forecastpv_new = filtered_fields(obj["metrics"],"forecastpv",True,s.forecastpv_file_name)
                if len(forecastpv_new)>0:
                    forecastpv_list = forecastpv_new
            #else:
            #    print ("No metrics in object:",obj)
            
"""
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
    global powerSystem
    async with sse_response(request) as resp:
        while True:
            #data = 'Server Time : {}'.format(datetime.now())
            status_obj = powerSystem.get_status(True)
            
            #print(data)
            #voisiko viimeisin update mennä globaaliin, jota tutkitaan vaikka sekunnin välein, jos uutta niin tulostetaan json
            await resp.send(json.dumps(status_obj))  
            while powerSystem.status_propagated:  
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
    global powerSystem

    obj = await request.json()
    #pp.pprint(obj)
   
    #TODO: different metrics could be parametrized, so addional metrics (eg. PV inverter data) could be added without code changes
    if "metrics" in obj:
        gridenergy_new = filtered_fields(obj["metrics"],"gridenergy",False)
        #this
        if len(gridenergy_new)==1: # there should be only one entry
            #
            #powerSystem.set_variables(gridenergy_new[0])
            powerSystem.print_variables() #debugging
            gridenergy_data = gridenergy_new[0]
            #TODO: trigger recalculate also after other updates but wait thats all requests in the incoming Telegraf buffer are processed
            recalculate()
        
        temperature_new = filtered_fields(obj["metrics"],"temperature",False)
        if len(temperature_new)>0:
            #powerSystem.set_variables(temperature_new)
            temperature_data = temperature_new
            process_sensor_data(temperature_data)
            
        dayahead_new = filtered_fields(obj["metrics"],"dayahead",False,s.dayahead_file_name)
        if len(dayahead_new)>0:
            dayahead_list = dayahead_new

        forecastpv_new = filtered_fields(obj["metrics"],"forecastpv",False,s.forecastpv_file_name)
        if len(forecastpv_new)>0:
            forecastpv_list = forecastpv_new

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
    

