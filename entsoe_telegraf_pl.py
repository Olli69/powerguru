#!/usr/bin/env python3
# coding: utf-8 

#Get day-ahead energy prices from Entsoe API and output stuff in a format readable by Telegraf
# Called few times a day (plus in startup) from Telegraf, results are resent to Powerguru and InfluDb


import settings as s
import time 
from datetime import datetime
from datetime import timedelta
from entsoe import EntsoePandasClient
import traceback #error reporting

import pandas as pd

# Telegraf plugin
from telegraf_pyplug.main import print_influxdb_format, datetime_tzinfo_to_nano_unix_timestamp

import sys
import pytz


powerguru_settings = s.read_settings(s.powerguru_file_name)
timeZoneLocal =  powerguru_settings["timeZoneLocal"]
EntsoEUAPIToken = powerguru_settings["EntsoEUAPIToken"]
SpotPriceArea = powerguru_settings["SpotPriceArea"]


tz_local = pytz.timezone(timeZoneLocal)


#part of the code from https://github.com/EnergieID/entsoe-py
def getNordPoolSPOTfromEntsoEU():
    if not EntsoEUAPIToken:
        print ("EntsoEU API Token undefined")
        return
        
    day_in_seconds = 3600*24
    #first hour of this day    
    dt = datetime.fromtimestamp(int(time.time()/(3600*24))*(3600*24)-3600)

    start1 = tz_local.localize(dt)
  #  start1 = pd.Timestamp(start1,tz=timeZoneLocal)
    start1 = pd.Timestamp(dt,tz=timeZoneLocal)
    end1 = pd.Timestamp(dt,tz=timeZoneLocal)
    end1 = end1 + timedelta(days=3) # can be a bit longer in the future, you get what you get

    #if type(start) != pd.Timestamp or type(end) != pd.Timestamp:
    #print ("start1:",type(start1))
    #print ("end1:",type(end1))


   
    country_code = SpotPriceArea  
    tag_name = "dayahead"
    try:
        #print ("Querying - country code: {:s}, start: {:s}, end: {:s}".format(country_code, start1.strftime("%Y-%m-%dT%H:%M:%S"),end1.strftime("%Y-%m-%dT%H:%M:%S")))  
        client = EntsoePandasClient(EntsoEUAPIToken)
        # methods that return Pandas Series
        ts =client.query_day_ahead_prices(country_code, start=start1,end=end1)

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception( exc_type,exc_value, exc_traceback,limit=5, file=sys.stdout)
        print ("Cannot get prices 1", sys.exc_info())
        return
    	
    try:
        for tr in ts.keys():
            trdt = tr.to_pydatetime()   
            energyPriceSpot = (ts[tr]/10) #+s.spotMarginPurchase
 
            print_influxdb_format(
                measurement="spot",
                #fields={"energyPriceSpot":energyPriceSpot,"energyPrice":energyPrice,"transferPrice": transferPrice,"totalPrice":totalPrice },
                fields={"energyPriceSpot":energyPriceSpot},
                tags = { "priceArea": SpotPriceArea, "name" : tag_name},
                nano_timestamp=datetime_tzinfo_to_nano_unix_timestamp(trdt)
            )  

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback.print_exception( exc_type,exc_value, exc_traceback,limit=5, file=sys.stdout)
        print ("Cannot get prices 2", sys.exc_info())
        return
		

getNordPoolSPOTfromEntsoEU()


         

	