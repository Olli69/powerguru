#!/usr/bin/env python

#Get solar energy forecast from www.bcdcenergia.fi and outputs it in format readable by Telegraf

import requests
import json
import settings as s
import time
from datetime import datetime, timezone,date

# Telegraf plugin
from typing import Dict
from telegraf_pyplug.main import print_influxdb_format, datetime_tzinfo_to_nano_unix_timestamp


from datetime import timedelta
import dateutil.parser

import sys
import pytz

tz_local = pytz.timezone(s.timeZoneLocal)


# report
def forecast_to_telegraf():
    query_data_raw = 'action=getChartData&loc=' + s.bcdcenergiaLocation
    r = requests.post('http://www.bcdcenergia.fi/wp-admin/admin-ajax.php',data=query_data_raw,headers={'Content-Type': 'application/x-www-form-urlencoded'})
    fcst_data = json.loads(r.text)
    day_value = 0.0
    for pv_h in fcst_data["pvenergy"]:
        day_value += pv_h["value"]
    #print ("Total forecast references value for {:s} is {:f}.".format(fcst_data["startdate"],day_value))
    
	#ifclient = InfluxDBClient(host=s.ifHost, port=s.ifPort, username=s.ifUsername, password=s.ifPassword, ssl=s.ifssl, verify_ssl=s.ifVerify_ssl,timeout=s.ifTimeout, database=s.ifDatabase)

    i=0
    try:
        json_body = []
        daytsprev = -1
        daytotal = 0.0
        METRIC_NAME: str = "solarfcst"
        tag_name = "forecastpv"
        #print ((fcst_data["pvenergy"]))
        
        for pv_h in fcst_data["pvenergy"]:
            #print(pv_h)
            #print(int(pv_h["time"]))
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
                    tags = { "location": s.bcdcenergiaLocation},
                    nano_timestamp=datetime_tzinfo_to_nano_unix_timestamp(loc_dtday)
                )         
                daytotal = 0.0
            
            daytsprev = daytscur
            dt = datetime.fromtimestamp(int(pv_h["time"]/1000))
            loc_dt = tz_local.localize(dt) 
            
            print_influxdb_format(
            measurement=METRIC_NAME, 
            tags = { "location": s.bcdcenergiaLocation,  "name" : tag_name},
            fields={"pvrefvalue":pv_h["value"]+0.0,"pv_forecast":pv_h["value"]*30.0/2.5},
            nano_timestamp=datetime_tzinfo_to_nano_unix_timestamp(loc_dt)
            )

    #todo: error handling järkeväksi
    except:
        print ("Cannot write to influx", sys.exc_info())
		


forecast_to_telegraf() 



         

	