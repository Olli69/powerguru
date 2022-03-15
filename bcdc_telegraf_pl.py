#!/usr/bin/env /usr/bin/python3.9

#Get solar energy forecast from www.bcdcenergia.fi and outputs it in format readable by Telegraf
# Called few times a day (plus in startup) from Telegraf, results are resent to Powerguru and InfluDb

import requests
import json
import settings as s
from datetime import datetime

# Telegraf plugin
from typing import Dict
from telegraf_pyplug.main import print_influxdb_format, datetime_tzinfo_to_nano_unix_timestamp

import sys
import pytz

powerguru_settings = s.read_settings(s.powerguru_file_name)
timeZoneLocal =  powerguru_settings["timeZoneLocal"]
#bcdcenergiaLocation = powerguru_settings["bcdcenergiaLocation"]
bcdcLocationsHandled = powerguru_settings["bcdcLocationsHandled"]

  

tz_local = pytz.timezone(timeZoneLocal)


# report
def forecast_to_telegraf(location):
    query_data_raw = 'action=getChartData&loc=' + location
    r = requests.post('http://www.bcdcenergia.fi/wp-admin/admin-ajax.php',data=query_data_raw,headers={'Content-Type': 'application/x-www-form-urlencoded'})
    fcst_data = json.loads(r.text)
    day_value = 0.0
    for pv_h in fcst_data["pvenergy"]:
        day_value += pv_h["value"]
    i=0
    try:
        daytsprev = -1
        daytotal = 0.0
        METRIC_NAME: str = "solarfcst"
        tag_name = "forecastpv"
        for pv_h in fcst_data["pvenergy"]:

            daytscur = int(pv_h["time"]/(3600000*24))
            daytotal += pv_h["value"]+0.0
            i += 1
            
            if daytsprev != -1 and (i==len(fcst_data["pvenergy"])): #jos näin, niin vois olla vikana
                dtday = datetime.fromtimestamp(daytscur*3600*24+(12*3600))
                loc_dtday = tz_local.localize(dtday)

                METRIC_FIELDS: Dict[str, int] = {"pvrefday":daytotal}
                print_influxdb_format(
                    measurement=METRIC_NAME,
                    fields=METRIC_FIELDS,
                    tags = { "location": location},
                    nano_timestamp=datetime_tzinfo_to_nano_unix_timestamp(loc_dtday)
                )         
                daytotal = 0.0
            
            daytsprev = daytscur
            dt = datetime.fromtimestamp(int(pv_h["time"]/1000))
            loc_dt = tz_local.localize(dt) 
            
            print_influxdb_format(
            measurement=METRIC_NAME, 
            tags = { "location": location,  "name" : tag_name},
            fields={"pvrefvalue":pv_h["value"]+0.0,"pv_forecast":pv_h["value"]*30.0/2.5},
            nano_timestamp=datetime_tzinfo_to_nano_unix_timestamp(loc_dt)
            )

    #TODO: error handling järkeväksi
    except:
        print ("Cannot write to influx", sys.exc_info())
		
for location in bcdcLocationsHandled:
    forecast_to_telegraf(location)





         

	
