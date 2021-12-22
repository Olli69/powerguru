#!/usr/bin/env python
import sys
import dateutil.parser
#import httplib
#import http.client
import signal
import time

import pytz 
import settings as s #settings file
import random

import os
import re
from glob import glob #Unix style pathname pattern expansion

import argparse #command line argument library, maybe needed later

try:
    # Redis is an in-memory data structure store, used as a distributed, in-memory key–value database
    # this is optional, values are not used yet
    import redis 
except ImportError:
    redis = None 
        

import json

from datetime import datetime, timezone,date

import RPi.GPIO as GPIO # handle Rpi GPIOs for connected to relays

#Twisted is an event-driven networking engine
from twisted.internet import task
from twisted.internet import reactor


# ModBus libraries
from pymodbus.constants import Endian
from pymodbus.constants import Defaults
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.client.sync import ModbusSerialClient as ModbusClient
from pymodbus.transaction import ModbusRtuFramer

# basic settings
import pprint
pp = pprint.PrettyPrinter(indent=4)

#InfluxDB librarys
from influxdb import InfluxDBClient


#TODO: - epsilon lämpöihin

# Mittauksen jälkeen katsotaan mitkä ehdot (conditions) päällä
# Kun tiedetään contitions, niin katsotaan mitkä targetit täyttyneet ja mitkä eivät.
# Ne targetit jotka eivät toteutuneet (eli varaajan lämpö alhaisempi kuin sen hetken tavoite) pyritään toteuttamaan laittamaan actuator päälle (eli käytännössä nostetaan relen gpio päälle).

importTot = 0
imports = [0,0,0]

client_modbus = None

pricesAndForecast = None
lastPriceHour = -1

previousTotalEnergyHour = -999
previousTotalEnergy = -1
hourMeasurementCount = 0
hourCumulativeEnergyPurchase = 0


tz_local = pytz.timezone(s.timeZoneLocal)

# global variables
actuators = []
sensorData = None
lineResource = None

#use GPIO-numbers to refer GPIO pins
GPIO.setmode(GPIO.BCM)



# get current prices and expected future solar, e.g. solar6h is solar within next 6 hours
def getPriceAndForecast(ifclient):
    dtnow = datetime.now()
    now_local = dtnow.astimezone(tz_local).isoformat()
    local_time = now_local[11:19]
    if s.daytimeStarts < local_time < s.daytimeEnds:
        transferPrice = s.transferPriceDay
        energyPrice = s.energyPriceDay
    else:
        transferPrice = s.transferPriceNight
        energyPrice = s.energyPriceNight
            
    totalPrice = transferPrice+s.electricityTax+energyPrice
    
    
    try: 
        results = ifclient.query(('SELECT last(energyPriceSpot) as energyPriceSpot FROM "nordpool" WHERE time < %ds fill(null)') % (time.time()) )
        pricets = list(results.get_points())
        energyPriceSpot =  pricets[0]["energyPriceSpot"]
    except:
        energyPriceSpot = 0
        print ("Cannot read energyPriceSpot from influx", sys.exc_info())
        
    solar6h = 0
    solar12h = 0
    solar18h = 0
    solar24h = 0
    try: 
        results = ifclient.query(('SELECT pvrefvalue FROM "bcdcenergia" WHERE time > %ds fill(null)') % (time.time() ))
        fcstts = list(results.get_points())
        for fcst_row in fcstts:
            timest = fcst_row["time"]
           
            timedt = dateutil.parser.parse(fcst_row["time"])
            timest=  datetime.timestamp(timedt)
            
            
            if timest < time.time()+(24*3600):
                solar24h += fcst_row["pvrefvalue"]
                
            if timest < time.time()+(18*3600):
                solar18h += fcst_row["pvrefvalue"]
                
            if timest < time.time()+(12*3600):
                solar12h += fcst_row["pvrefvalue"]
                
            if timest < time.time()+(6*3600):
                solar6h += fcst_row["pvrefvalue"]
                
    except:
        print ("Cannot read energy forecast from influx", sys.exc_info())
        
    return {"transferPrice": transferPrice, "energyPrice" : energyPrice, "totalPrice" :totalPrice, "energyPriceSpot" : energyPriceSpot
            , "solar6h": solar6h, "solar12h": solar12h,"solar18h": solar18h, "solar24h" : solar24h}





# This class handles line resources (phases) e.g.
class LineResource:
    def __init__(self):
        self.lines = [ (1, 0),(2, 0),(3, 0)]
        self.lines_sorted = self.lines
      #  self.lines_sorted = self.lines.sorted(self.lines, key=lambda line: line[1]) 

    
    def setLoad(self,importL1A,importL2A,importL3A): # tällä voisi asettaa mittausten luvun jälkeen nykyisen kuorman
        # jos joku ylittää sallitun kuorman voisi käydä katkomassa
        self.lines = [ (1, importL1A),(2, importL2A),(3, importL3A)]
        
        # overload control
        # check each line, if overload -> decrease load (if possible) until no overload exists
        for line in self.lines:
            overLoad = line[1]-s.basicInfo["maxLoadPerPhaseA"]
            if overLoad<0:
                continue
            
            for actuator in actuators:
                for act_line in actuator.lines:
                    if act_line.get("l",-1)==-1:
                        print("********************")
                        print("act_line attribute l undefined:")
                        pp.pprint(act_line)
                        
                    if line[0]==act_line.get("l",-1) and act_line["up"] and overLoad>0:
                        print("OVERLOAD, line {:d} lowering down, releasing {:d} A".format(line[0],act_line["A"] ))
                        act_line["up"]  = False
                        GPIO.output(act_line["gpio"], GPIO.LOW)
                        overLoad -= act_line["A"]
                        
        self.lines_sorted = sorted(self.lines, key=lambda line: line[1]) 
        print("setLoad")
        pp.pprint(self.lines_sorted)

        return self.lines_sorted
    
    def getLineCapacity(self): # antaa vähiten kuormitetuimmat linjat ekaksi
        available_lines = []
        for line in self.lines_sorted:
            #if (line[1]+A)<s.basicInfo["maxLoadPerPhaseA"]:
            available_lines.append({"l" : line[0],"availableA":s.basicInfo["maxLoadPerPhaseA"]-line[1]})
        return available_lines #näitä voisi kuormittaa jos ei ole jo kuormitettu
                
# Stores sensor values (from thermometers)
class SensorData:
    def __init__(self, sensors):
        self.sensors = []
        for sensor in sensors:
            self.sensors.append({"code":sensor["code"],"type": sensor["type"],"id" : sensor["id"],"desc" :sensor.get("desc",""),"value":None })
            
        pp.pprint(self.sensors)   
         
    def setValueById(self,id,value):    
        for sensor in self.sensors:
            if sensor["id"] == id:
                sensor["value"]= value
                return
                
    def getValueByCode(self,code):    
        for sensor in self.sensors:
            if sensor["code"] == code:
             #   print ("getValueByCode ",sensor["code"], "  ", sensor["value"] )
                return sensor["value"]
            
        return None

  
       
# Actuator can be e.g. one boiler with 1 or 3 lines (phases)
class Actuator:  
    def __init__(self, code, data):
        pp.pprint(code) 
        self.code = code
        self.reverse_output = data.get("reverse_output",False) #esim. lattialämmityksen poissa-kytkin, todo gpio-handleen
        
        self.lines = [{"l" : 1, "gpio" : None, "A" : 0 ,"up": False},{"l" : 2, "gpio" : None, "A" : 0,"up": False },{"l" : 3, "gpio" : None, "A" : 0,"up": False }]
        
        self.targets = []

        for line in data["lines"]:
            ln = {"l" : line["l"], "gpio" : line["gpio"], "A" : line.get("A",0),"up": False }
            lineInd = line["l"]-1 #HUOM INDEKSOINTI
            self.lines[lineInd] = ln
            
            GPIO.setup(ln["gpio"], GPIO.OUT)
            #TODO:: nyt olisi hyvä hetki ajaa GPIOT alas, jos jääneet ylös ennestään
            GPIO.output(ln["gpio"],GPIO.HIGH if ln["up"] else GPIO.LOW)
          
        for target in data["targets"]:
            tn = {"condition" : target["condition"], "sensor" : target["sensor"], "valueabove": target.get("valueabove",None), "valuebelow": target.get("valuebelow",None)}
            self.targets.append(tn) 
        # reset gpios
        pass
    
    
    def getTarget(self,conditionList):
        # get first matching
        for target in self.targets:
            if target["condition"] in conditionList:
                sersorValue = sensorData.getValueByCode(target["sensor"])
                
                if sersorValue is None:
                    return {"condition" : target["condition"],"reached":None, "error": True, "sersorValue":None}
      
                # now we know that condition match and sensor has a value, so we check if the target is reached 
                targetReached = True
         
                valueabove = target.get("valueabove",None)
                valuebelow = target.get("valuebelow",None)
                
                targetTemp = valueabove if valueabove is not None else valuebelow
                
                if target["valueabove"] is not None:
                    if sersorValue< target["valueabove"]:
                        
                        targetReached = False
                
                if targetReached and target["valuebelow"] is not None:
                    if sersorValue> target["valuebelow"]:
                        targetReached = False
                        
                return {"condition" : target["condition"],"reached":targetReached, "error": False
                        , "sersorValue":sersorValue,"actuatorCode":self.code,"valueabove" : valueabove,"valuebelow":valuebelow, "targetTemp" : targetTemp}
        
        return {"condition" : None,"reached":None, "error": False} # no matching target
    
    def loadUp(self):
        lineResources = lineResource.getLineCapacity()
        #todo:oikea järjestys
        # pp.pprint(lineResources)
        # print(self.code, " loadUp")
        for l in range(3):
            #kesken
            line = lineResources[l]["l"]-1
            if self.lines[line].get("up",False):
                pass 
               # print("line {:d} already up".format(l+1))
            elif lineResources[line]["availableA"]>10:  #kaiva amppeerimäärä laitteelta/linjalta
                print("line {:d} raising up with {:d} A".format(line+1,self.lines[line]["A"]))
                self.lines[line]["up"] = True
                GPIO.output(self.lines[line]["gpio"],GPIO.HIGH if self.lines[line]["up"] else GPIO.LOW)
                return self.lines[line]["A"]
         
        return 0

   
         
    # check if available lines, if not return 0
    # check which line to increase
    #return increased power in A, 0 if nothing to descrease
    
    def loadDown(self):
        lineResources = lineResource.getLineCapacity() #katso saisiko ton amppeerimäärän laitteelta
      #  print(self.code, " loadDown")
        for l in range(2,-1,-1): 
            line = lineResources[l]["l"]-1
            if not self.lines[line].get("up",False):
                pass
                #print("line {:d} already down".format(l+1))
            else:
                print("line {:d} lowering down, releasing {:d} A".format(line+1,self.lines[line]["A"]))
                self.lines[line]["up"] = False
                GPIO.output(self.lines[line]["gpio"],GPIO.HIGH if self.lines[line]["up"] else GPIO.LOW)
                return -self.lines[line]["A"]
         
        return 0
    

    # if line defined decrease only if this line is high - load regulation (eli jos vaiheessa ylikuormaa , koskee vain tätä vaihetta)
    # check if current power > 0, if not return 0
    # check which line to decrease
    #return decreased power in A, 0 if nothing to descrease
    
    
#- - - - - - - - -
# set Modbus defaults
Defaults.UnitId = s.MB_ID
Defaults.Retries = 5

class FieldObj(object):
    pass



# Function that returns array with IDs of all found thermometers
def find_thermometers():
    # Get all devices
    w1Devices = glob(s.w1DeviceFolder + '/*/')
    # Create regular expression to filter only those starting with '28', which is thermometer
    w1ThermometerCode = re.compile(r'28-\d+')
    # Initialize the array
    thermometers = []
    # Go through all devices
    for device in w1Devices:
        # Read the device code
        deviceCode = device[len(s.w1DeviceFolder)+1:-1]
        # If the code matches thermometer code add it to the array
        if w1ThermometerCode.match(deviceCode):
            thermometers.append(deviceCode)
    # Return the array
    return thermometers


# Function that reads and returns the raw content of 'w1_slave' file
def read_temp_raw(deviceCode):
    f = open(s.w1DeviceFolder + '/' + deviceCode + '/w1_slave' , 'r')
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
        # Convert the temperature to Fahrenheit
        temp_f = temp_c * 9.0 / 5.0 + 32.0
        # Return formatted sensor data
        return {
            'thermometerID': deviceCode,
            'celsius': temp_c,
            'fehrenheit': temp_f
        }


print ("Connecting influx")
        
#TODO: virhehavainnointi kytkentäään ja siihen jos yhteys katkennut
ifclient = InfluxDBClient(host=s.ifHost, port=s.ifPort, username=s.ifUsername, password=s.ifPassword, ssl=s.ifssl, verify_ssl=s.ifVerify_ssl, timeout=s.ifTimeout, database=s.ifDatabase)

thermometers = find_thermometers()

 
def sig_handler(signum, frame):
    reactor.callFromThread(reactor.stop)
    client_modbus.close()

        
def check_conditions(importTot):
  #  global s.conditions
    ok_conditions = []
    global hourCumulativeEnergyPurchase
    # get the standard UTC time  
   

    dtnow = datetime.now()

   # local_dt = dtnow.replace(tzinfo=timezone.utc).astimezone(tz=None).isoformat()
   # localtime = time.localtime(time.time())
    now_local = dtnow.astimezone(tz_local).isoformat()
   # print(now_local)
    
    local_day = now_local[5:10]
    local_time = now_local[11:19]
    print("Imported {:.2f}, local_day {:s}, local_time {:s}".format(importTot,local_day,local_time))
    

    
    for key in s.conditions:
        ok = True
        condition = s.conditions[key]
        
        if "netsales" in condition.keys(): # check netsales condition
            if condition["netsales"]:
                if s.basicInfo["hourNetting"] and hourCumulativeEnergyPurchase> 0: #netpurchase
                    ok = False
                elif (not s.basicInfo["hourNetting"]) and importTot> -s.basicInfo["netSalesMaxExportkW"]:
                    ok = False
    
                
                
        if ok and "starttime" in condition.keys() and "endtime" in condition.keys(): # check time
            if condition["starttime"] > condition["endtime"]: # assume condition reaches over midnight
                if condition["endtime"] <local_time<condition["starttime"]:
                    ok = False
            elif (condition["endtime"] <local_time) or (local_time<condition["starttime"] ) :
                    ok = False
                    
        if ok and "dayfirst" in condition.keys() and "daylast" in condition.keys(): # check time
            if condition["dayfirst"] > condition["daylast"]: # assume condition reaches over midnight
                if condition["daylast"] <local_day<condition["dayfirst"]:
                    ok = False
            elif (condition["daylast"] <local_day) or (local_day<condition["dayfirst"] ) :
                    ok = False

        if ok and "solar12above" in condition.keys():
            if condition["solar12above"] >= pricesAndForecast["solar12h"]:
                ok = False 
         
            
        if ok and "solar12below" in condition.keys():
            if condition["solar12below"] < pricesAndForecast["solar12h"]:
                ok = False 
            
                                  
        if ok:
            ok_conditions.append(key) # the condition is ok if not filtered out by any rule
            
    pp.pprint (ok_conditions)
    return ok_conditions


def reportState(targetTempsReport): 
    tempp = {}
    state = {}

   
    try:
        json_body = []
        for targetTemp in targetTempsReport:
            tempp[ targetTemp["code"]]= targetTemp["targetTemp"]

        json_body.append( {
        "measurement": "targettemp",
        "time":  datetime.now(timezone.utc),
        "fields": tempp
        })

       # print("*")
       # pp.pprint(actuators)
        for actuator in actuators:
          #  pp.pprint(actuator.lines)
            i=0
            for line in actuator.lines:
                lineNumVal = 1 if line.get("up",False) else 0
                state[actuator.code +'L' + str(i+1)] = lineNumVal
                i+=1
                
        json_body.append( {
        "measurement": "relaystate",
        "time":  datetime.now(timezone.utc),
        "fields": state
        })

  
        ifclient.write_points(json_body)
        
       # print ("Wrote to influx")
    except:
         print ("Cannot write to influx", sys.exc_info())
         

# this is the main function called by Reactor event handler and defined in task.LoopingCall(doWork)    
def doWork():
    print ('###################################')
    global imports, importTot 
    global lineResource
    global pricesAndForecast,lastPriceHour
    global previousTotalEnergyHour, previousTotalEnergy,hourCumulativeEnergyPurchase, hourMeasurementCount
  
    mbus_read_ok = True 
    try:
        
        result = client_modbus.read_input_registers(0x00, 23*2+4) #2*9=18
        result2 = client_modbus.read_input_registers(0x032, 2+15*2)
    except Exception as err: 
        print ("Cannot read modbus")
        return
    
    if result.isError():
        print ("Cannot read modbus - isError")
        mbus_read_ok = False
 
    res =  [None] * (23+4+2+15) # initiating array ?


    if result and mbus_read_ok:
        try:
            decoder = BinaryPayloadDecoder.fromRegisters(result.registers,byteorder=Endian.Big, wordorder=Endian.Little)
       # except ModbusIOException as MBExc:
        except Exception as MBExc:
            print ("Cannot read modbus - decoder")
            mbus_read_ok = False
            #return
        if mbus_read_ok:
            idx=0
            loc=0
          #  apu = decoder.decode_16bit_float()
            for i in range(23):
                res[idx] = decoder.decode_32bit_int()
            #    print ("%d (%s): %d " % (loc,hex(loc), res[idx]))
                idx+=1
                loc+=2
                
            for i in range(4):
                res[idx] = decoder.decode_16bit_int()
              #  print ("%d (%s) : %d " % (loc,hex(loc), res[idx]))
                idx+=1
                loc+=1
            
    if result2 and mbus_read_ok:
        decoder2 = BinaryPayloadDecoder.fromRegisters(result2.registers,byteorder=Endian.Big, wordorder=Endian.Little)
        for i in range(2):
            res[idx] = decoder2.decode_16bit_int()
         #   print ("%d (%s) : %d " % (loc,hex(loc), res[idx]))
            idx+=1
            loc+=1
            
        for i in range(15):
            res[idx] = decoder2.decode_32bit_int()
         #   print ("%d (%s): %d " % (loc,hex(loc), res[idx]))
            idx+=1
            loc+=2
            

    storep = {}
    tempp = {}
       # Go through all connected thermometers
    
    loadsA = [0,0,0]

    dtnow = datetime.now()
    now_local = dtnow.astimezone(tz_local).isoformat()
    
    if pricesAndForecast == None or lastPriceHour != dtnow.hour:
        pricesAndForecast = getPriceAndForecast(ifclient)
        print(pricesAndForecast)
        lastPriceHour = dtnow.hour
 
    if mbus_read_ok:   
        for data_point in s.data_points:
 
            if 6 <= data_point["idx"] <= 8: #load per phase A
                loadsA[data_point["idx"]-6] = res[data_point["idx"]]/data_point["factor"]
            if 9 <= data_point["idx"] <= 11: #import per phase kW
                imports[data_point["idx"]-9] = res[data_point["idx"]]/data_point["factor"]
                
            # net purchase all, lines total    
            if data_point["idx"] == 20: #import total  kW
                importTot = res[data_point["idx"]]/data_point["factor"]
                # sales only for negative import
                storep[ "sale"]= (-importTot if importTot<0 else 0.0)
                storep[ "purchase"]= (importTot if importTot>0 else 0.0)
                    
                # yösähkö erikseen, tää olisi hyvä parametroida

                local_time = now_local[11:19] 
                #TODO nämä parametreistä
                if "07:00:00" < local_time < "22:00:00":# and dtnow.isoweekday()!=7: 
                    storep[ "purchaseDay"]= (importTot if importTot>0 else 0.0)
                    storep[ "purchaseNight"]= 0.0
                else:
                    storep[ "purchaseNight"]= (importTot if importTot>0 else 0.0)
                    storep[ "purchaseDay"]= 0.0
    
                # cost
                if importTot>0:
                    storep[ "cost"] = importTot*pricesAndForecast["totalPrice"]/100000
                else:
                    storep[ "cost"] = importTot*(pricesAndForecast["energyPriceSpot"]-s.spotMarginSales)/100000
            
            if data_point["idx"] == 29: #Total cumulative
                
                cumulativeEnergy = res[data_point["idx"]]/data_point["factor"]
                
                if previousTotalEnergy == -1: #first measurement after init
                    previousTotalEnergy = cumulativeEnergy
                    
                if previousTotalEnergyHour != dtnow.hour-1: #first measurement within hour
                    # TODO: could get exact number from the DB
                    previousTotalEnergyHour = dtnow.hour-1
                    hourMeasurementCount = 0
                 
                
                hourCumulativeEnergyPurchase = cumulativeEnergy-previousTotalEnergy
                storep["hourCumulativeEnergyPurchase"]= hourCumulativeEnergyPurchase               
                hourMeasurementCount +=1
                
                if hourMeasurementCount==1: #first measurement of hour, init cumulative
                    previousTotalEnergy = cumulativeEnergy
                
            
            if data_point["enabled"]==1:
                #print ("%s: %.2f %s " % (data_point["desc"],res[data_point["idx"]]/data_point["factor"], data_point["unit"]))
                storep[ data_point["desc"].replace(" ","")]= res[data_point["idx"]]/data_point["factor"]
                
        lineResource.setLoad(loadsA[0],loadsA[1],loadsA[2])             
 

  
    
    try:
        json_body = []
        if mbus_read_ok:
            json_body.append( {
                 "measurement": s.measurementIdElectricity,
                 "tags": {
                     "meteriId": s.meteriIdTag
                },
                "time":  datetime.now(timezone.utc),
                "fields": storep
        })
            
        for thermometer in thermometers:
            tempval = read_temp(thermometer)
            tempp[ thermometer]= tempval["celsius"]
            sensorData.setValueById(thermometer,  tempval["celsius"])
           
        json_body.append( {
        "measurement": s.measurementIdTemperature,
        "time":  datetime.now(timezone.utc),
        "fields": tempp
    })
        
        # pp.pprint(json_body)
        ifclient.write_points(json_body)

    except:
         print ("Cannot write to influxDB", sys.exc_info())
         
    
      
    current_conditions = check_conditions(importTot)
    
    if redis: # if redis loaded we will share conditions to in-memory database for other possible processes to use
        try:
            r = redis.Redis(host='localhost', port=6379, db=0, password=s.redisPassword)
            r.set('pg_conditions', json.dumps(current_conditions))
            r.set('pg_import',importTot)
        except:
            print ("Cannot write to redis", sys.exc_info())
    
    targetTempsReport = []
    
    for actuator in actuators:
        target = actuator.getTarget(current_conditions)
        targetTemp = target["targetTemp"]
        targetTempsReport.append({"code": actuator.code,"targetTemp":targetTemp} ) 
  
    random_actuators = actuators.copy()
    random.shuffle(random_actuators) # set up load in random order
    

    for actuator in random_actuators:
        target = actuator.getTarget(current_conditions)    
        if not target["reached"]:
            loadChange = actuator.loadUp() #
            if abs(loadChange) > 0: #only 1 v´chnage at one time, eli ei liikaa muutosta minuutissa
                break

        elif target["reached"]:
            print("Actuator {:s} ,condition {:s}, target reached ".format(actuator.code,target["condition"]))
            loadChange = actuator.loadDown()
            
            if abs(loadChange) > 0:
               # print ("loadDown loadChange:", loadChange)
                break
      
    # export to influxDB
    reportState(targetTempsReport)

 
def load_program_config(signum=None, frame=None):
    global actuators,sensorData,lineResource
    for act in s.actuators:
        actuator =  Actuator(act,s.actuators[act])
        actuators.append(actuator)
        
    sensorData = SensorData(s.sensors)
    lineResource = LineResource()       
    return None

def main(argv): 
    global client_modbus
    parser = argparse.ArgumentParser()
    # placeholder for future arguments
    parser.add_argument('-t', dest='testonly', action='store_true')
    args = parser.parse_args()
    
    load_program_config()    
    
    client_modbus = ModbusClient(method='rtu', port=s.SERIAL, stopbits=1, bytesize=8, timeout=0.25, baudrate=s.BAUD, parity='N')
    connection = client_modbus.connect()
 
    signal.signal(signal.SIGINT, sig_handler)
    
    l = task.LoopingCall(doWork)
    l.start(s.READ_INTERVAL)
    
    # start event loop, e.g. doWork process
    reactor.run()

if __name__ == "__main__":
    main(sys.argv[1:])
    
    
