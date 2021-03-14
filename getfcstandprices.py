#!/usr/bin/env python
import requests
import json
import settings as s
import time


from datetime import datetime, timezone,date

from datetime import timedelta
import dateutil.parser

from entsoe import EntsoeRawClient
from entsoe import EntsoePandasClient

import pandas as pd


from influxdb import InfluxDBClient
import sys
import pprint
import pytz
pp = pprint.PrettyPrinter(indent=4)

tz_local = pytz.timezone(s.timeZoneLocal)


#part of the code from https://github.com/EnergieID/entsoe-py
def getNordPoolSPOTfromEntsoEU():
	if not s.EntsoEUAPIToken:
		print ("EntsoEU API Token undefined")
		return
		
	json_body = []
	dt = datetime.fromtimestamp(int(time.time()/(3600*24))*(3600*24)-3600)
	nowdt = datetime.now()
	
	
	start1 = tz_local.localize(dt)
	end1 = pd.Timestamp(dt,tz=s.timeZoneLocal)
	end1 = end1 + timedelta(days=1)
	
	print ("nowdt.hour = {:d}".format(nowdt.hour))
	if (nowdt.hour>11):
		start1 = start1 + timedelta(days=1)
		end1 = end1 + timedelta(days=1)
		
	#end1 =  copy.copy(start1) + timedelta(days=1)
				 
	
	print (start1,'->',end1)
	print (nowdt.hour,":" , nowdt.minute)
	 
	country_code = s.NordPoolPriceArea  
	try:
		print ("Querying - country code: {:s}, start: {:s}, end: {:s}".format(country_code, start1.strftime("%Y-%m-%dT%H:%M:%S"),end1.strftime("%Y-%m-%dT%H:%M:%S")))  
		client = EntsoePandasClient(s.EntsoEUAPIToken)
	# methods that return Pandas Series
		print ("Client ok")
	
		ts =client.query_day_ahead_prices(country_code, start=start1,end=end1)
		print ("Querying entsoe.eu ok")
	except:
		print ("Cannot get prices", sys.exc_info())
		return
		
	try:
		for tr in ts.keys():
			
			now_local = tr.isoformat()
			local_time = now_local[11:19]
			if s.daytimeStarts < local_time < s.daytimeEnds:# and tr.isoweekday()!=7:
				transferPrice = s.transferPriceDay
				energyPrice = s.energyPriceDay
			else:
				transferPrice = s.transferPriceNight
				energyPrice = s.energyPriceNight
			
			totalPrice = transferPrice+s.electricityTax+energyPrice
			energyPriceSpot = (ts[tr]/10) #+s.spotMarginPurchase
			#totalPriceSpot = transferPrice+s.electricityTax +energyPriceSpot
			json_body.append({
				"measurement": "nordpool",
				"time":  int(tr.timestamp()*1000000000),
				"fields": {"energyPriceSpot":energyPriceSpot,"energyPrice":energyPrice,"transferPrice": transferPrice,"totalPrice":totalPrice }})
			
		ifclient = InfluxDBClient(host=s.ifHost, port=s.ifPort, username=s.ifUsername, password=s.ifPassword, ssl=s.ifssl, verify_ssl=s.ifVerify_ssl,timeout=s.ifTimeout, database=s.ifDatabase)
		pp.pprint(json_body)
		ifclient.write_points(json_body)
		print ("Updating InfluxDB ok -probably")

	except:
		print ("Cannot get prices", sys.exc_info())
		

def getBCDCSolarForecast():
	query_data_raw = 'action=getChartData&loc=' + s.bcdcenergiaLocation
	r = requests.post('http://www.bcdcenergia.fi/wp-admin/admin-ajax.php',data=query_data_raw,headers={'Content-Type': 'application/x-www-form-urlencoded'})

	fcst_data = json.loads(r.text)
	day_value = 0.0
	for pv_h in fcst_data["pvenergy"]:
		day_value += pv_h["value"]
	print ("Total forecast references value for {:s} is {:f}.".format(fcst_data["startdate"],day_value))
	return fcst_data

# report
def ExportForecast2InfluxDB(fcst_data):
	ifclient = InfluxDBClient(host=s.ifHost, port=s.ifPort, username=s.ifUsername, password=s.ifPassword, ssl=s.ifssl, verify_ssl=s.ifVerify_ssl,timeout=s.ifTimeout, database=s.ifDatabase)

	i=0
	try:
		json_body = []
		daytsprev = -1
		daytotal = 0.0

		print ((fcst_data["pvenergy"]))
		for pv_h in fcst_data["pvenergy"]:
			print(pv_h)
			print(int(pv_h["time"]))
			daytscur = int(pv_h["time"]/(3600000*24))
			daytotal += pv_h["value"]+0.0
			i += 1
			
			if daytsprev != -1 and (i==len(fcst_data["pvenergy"])): #jos näin, niin vois olla vikana
				dtday = datetime.fromtimestamp(daytscur*3600*24+(12*3600))
				loc_dtday = tz_local.localize(dtday)
				print ("append day total")
				print (daytotal)
				json_body.append( {
					"measurement": "bcdcenergia",
					"time":  int(loc_dtday.timestamp()*1000000000),
					"fields": {"pvrefday":daytotal}
					})
				daytotal = 0.0			
				
			daytsprev = daytscur
			dt = datetime.fromtimestamp(int(pv_h["time"]/1000))
			loc_dt = tz_local.localize(dt)

			json_body.append( {
					"measurement": "bcdcenergia",
					"time":  int(loc_dt.timestamp()*1000000000),
					"fields": {"pvrefvalue":pv_h["value"]+0.0,"pv_forecast":pv_h["value"]*30.0/2.5}
					})

		
		pp.pprint(json_body)
		ifclient.write_points(json_body)
	
	except:
		print ("Cannot write to influx", sys.exc_info())
		

print ("****Fetching prices:")
getNordPoolSPOTfromEntsoEU()

print ("****Fetching forecast:")
fcst_data = getBCDCSolarForecast()
ExportForecast2InfluxDB(fcst_data) 



         

	