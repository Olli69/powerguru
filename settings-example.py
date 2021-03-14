
basicInfo = {"maxLoadPerPhaseA" : 50 #allow max this current per phase, if higher try to cut load
             ,"netSalesMaxExportkW": 1000 # this parameter has an important purpose, just do not remember what :)
             } 


timeZoneLocal = "Europe/Helsinki"


#influxDb variables
ifHost = 'myifhost.mydomain.com' # InfluxDB host name
ifPort = 8086               # InfluxDB port
ifUsername= 'admin'         # InfluxDB
ifPassword= 'password'      # InfluxDB password
ifssl=False                 # InfluxDB is ssl used
ifVerify_ssl=False          # InfluxDB is ssl certificate verified
ifTimeout=10                # InfluxDB connection timeout
ifDatabase ='mydatabase'         # InfluxDB database name

#InfluxDB ids and tags
meteriIdTag = "569-1"
measurementIdElectricity = "energy"
measurementIdTemperature = "boilertemp"

bcdcenergiaLocation = "Salo" # check you nearest location at http://www.bcdcenergia.fi/


# settings for USB-RS485 adapter for the power meter reading
SERIAL = '/dev/serial0'# '/dev/ttyUSB0'
BAUD = 9600
# settings for SDM630 Modbus
MB_ID = 1
READ_INTERVAL = 60          # ModBus read interval in seconds

# 1-wire from https://gitlab.com/bambusekd-dev-blog/raspberry-1-wire-temperature-ds18b20/-/blob/master/w1-read-temperature-ds18b20.py
# Folder with 1-Wire devices
w1DeviceFolder = '/sys/bus/w1/devices'


# Redis is an in-memory data structure store, used as a distributed, in-memory key–value database
redisPassword = 'dc9f03clkedflö0234rfokdlösfklöwef90ewdsafsada'

#Entso EU API, request this key from EntsoEU web site
EntsoEUAPIToken = ''
NordPoolPriceArea = 'FI'

# Pricing parameters, Finnish pricing and tax model
transferPriceDay = 3.59     # transfer price c/kWh, daytime,  YOUR PRICE HERE
transferPriceNight = 2.21   # transfer price c/kWh, nighttime,  YOUR PRICE HERE
energyPriceDay = 6.00       # energy price c/kWh, daytime , YOUR PRICE HERE
energyPriceNight = 4.50     # energy price c/kWh, nighttime, , YOUR PRICE HERE     
electricityTax =2.253       # electricity price c/kWh, Finnish taxation model
spotMarginPurchase = 0.24   # if SPOT agreement in purchase, your margin to the seller 
spotMarginSales = 0.24      # if SPOT agreement in sales, your margin to the buyer 
vatFactor = 1.24            # VAT factor, 24% -> 1.24

daytimeStarts = "07:00:00"
daytimeEnds = "22:00:00"




# parameters for conditions, multiple conditions can be true at the same time
conditions = {"sun": {"netsales": True, "desc":""} # we are selling energy, try to use more
              ,"sunnydaycoming": {"starttime": "04:00:00", "endtime": "07:00:00", "solar12above": 5.0, "desc":"sunny day coming (do not overheat the boilers now)"}   
              , "darkdaycoming": {"starttime": "04:00:00", "endtime": "07:00:00", "solar12below": 5.0, "desc":"dark day coming (heat the boilers, there will be no cheap energy today)"}        
              ,"morning": {"starttime": "07:00:00", "endtime": "10:00:00","desc":"varaajat levossa, aurinkoyösähköä odotellessa ainakin kesällä"}
              ,"evening": {"starttime": "18:30:00", "endtime": "22:05:00","desc":"varaajat levossa, yösähköä odotellessa"}
              ,"cooling1": {"starttime": "04:30:00", "endtime": "09:30:00","desc":"lasketaan lauhdevaraajan lämpöä ennen maidon jäähdytystä"}
              ,"cooling2": {"starttime": "13:30:00", "endtime": "18:30:00","desc":"lasketaan lauhdevaraajan lämpöä ennen maidon jäähdytystä"}
              ,"summernight": {"starttime": "22:00:00", "endtime": "07:00:00","dayfirst" : "02-15","daylast" : "10-15", "desc":""}
              ,"winternight1": {"starttime": "22:00:00", "endtime": "04:00:00","dayfirst" : "10-16","daylast" : "02-14", "desc":""}
              ,"winternight": {"starttime": "22:00:00", "endtime": "07:00:00","dayfirst" : "10-16","daylast" : "02-14", "desc":""}
              ,"day": {"starttime": "07:00:00", "endtime": "22:00:00" ,"desc":""}}


 
# actuators (heaters)
# b1 - boiler1, b2- boiler2
# l - phase/line
# pgio - rpi gpio for the control switch
# A - load
# targets:
#    - condition  - condion code to match
#    - sensor     - sensor the value is applied
#    - valueabove - target value of the sensor, i.e. temperature shoud be above this if the condition is true
actuators = {"b1": {"lines":[{"l": 1, "gpio": 16,"A":10},{"l": 2, "gpio": 5, "A":10},{"l": 3, "gpio": 6, "A":10}]
                    ,"targets":[
                         {"condition" : "winternight1", "sensor" : "b1out", "valueabove": 40} 
                        , {"condition" : "winternight", "sensor" : "b1out", "valueabove": 30} 
                        , {"condition" : "cooling1", "sensor" : "b1out", "valueabove": 15}  
                        , {"condition" : "cooling2", "sensor" : "b1out", "valueabove": 15} 
                        , {"condition" : "sun", "sensor" : "b1out", "valueabove": 35} 
                        , {"condition" : "morning", "sensor" : "b1out", "valueabove": 15} 
                        , {"condition" : "evening", "sensor" : "b1out", "valueabove": 15} 
                        , {"condition" : "summernight", "sensor" : "b1out", "valueabove": 30} 
                        , {"condition" : "day", "sensor" : "b1out", "valueabove": 15} ]
                    }
             ,"b2": {"lines":[{"l": 1, "gpio": 23,"A":10},{"l": 2, "gpio": 24, "A":10},{"l": 3, "gpio": 25, "A":10}] 
                     ,"targets":[
                          {"condition" : "sun", "sensor" : "b2out", "valueabove": 80} 
                        , {"condition" : "darkdaycoming", "sensor" : "b2out", "valueabove": 75} 
                        , {"condition" : "morning", "sensor" : "b2out", "valueabove": 50} 
                        , {"condition" : "evening", "sensor" : "b2out", "valueabove": 60} 
                        , {"condition" : "summernight", "sensor" : "b2out", "valueabove": 60}   
                        , {"condition" : "winternight", "sensor" : "b2out", "valueabove": 70} 
                        , {"condition" : "day", "sensor" : "b2out", "valueabove": 50} ]
                    }}


#temperature sensors, map 1-wire id:s to codes, only type "1-wire" is implemented
sensors = [ {"code":"b1out", "type": "1-wire", "id": "28-0417a23d60ff", "desc":"lauhdutinvaraaja ulos"}, {"code":"b2out", "type": "1-wire", "id": "28-0417a24c51ff", "desc":"tulistettu ulos"}]

           
# these are the datapoints from electrity meter read by modbus functions   
# only data point with enabled=1 are stored 
data_points = [{ "idx" : 0, "loc" : 0,  "desc" : "V L1-N",   "type" : "int32",  "unit" : "V",  "factor" : 10, "enabled" : 1 },
{ "idx" : 1, "loc" : 2,  "desc" : "V L2-N",   "type" : "int32",  "unit" : "V",  "factor" : 10, "enabled" : 0 },
{ "idx" : 2, "loc" : 4,  "desc" : "V L3-N",   "type" : "int32",  "unit" : "V",  "factor" : 10, "enabled" : 0 },
{ "idx" : 3, "loc" : 6,  "desc" : "V L1-L2",   "type" : "int32",  "unit" : "V",  "factor" : 10, "enabled" : 0 },
{ "idx" : 4, "loc" : 8,  "desc" : "V L2-L3",   "type" : "int32",  "unit" : "V",  "factor" : 10, "enabled" : 0 },
{ "idx" : 5, "loc" : 10,  "desc" : "V L3-L1",   "type" : "int32",  "unit" : "V",  "factor" : 10, "enabled" : 0 },
{ "idx" : 6, "loc" : 12,  "desc" : "A L1",   "type" : "int32",  "unit" : "A",  "factor" : 1000, "enabled" : 1 },
{ "idx" : 7, "loc" : 14,  "desc" : "A L2",   "type" : "int32",  "unit" : "A",  "factor" : 1000, "enabled" : 1 },
{ "idx" : 8, "loc" : 16,  "desc" : "A L3",   "type" : "int32",  "unit" : "A",  "factor" : 1000, "enabled" : 1 },
{ "idx" : 9, "loc" : 18,  "desc" : "kW L1",   "type" : "int32",  "unit" : "W",  "factor" : 10, "enabled" : 1 },
{ "idx" : 10, "loc" : 20,  "desc" : "kW L2",   "type" : "int32",  "unit" : "W",  "factor" : 10, "enabled" : 1 },
{ "idx" : 11, "loc" : 22,  "desc" : "kW L3",   "type" : "int32",  "unit" : "W",  "factor" : 10, "enabled" : 1 },
{ "idx" : 12, "loc" : 24,  "desc" : "kVA L1",   "type" : "int32",  "unit" : "VA",  "factor" : 10, "enabled" : 1 },
{ "idx" : 13, "loc" : 26,  "desc" : "kVA L2",   "type" : "int32",  "unit" : "VA",  "factor" : 10, "enabled" : 1 },
{ "idx" : 14, "loc" : 28,  "desc" : "kVA L3",   "type" : "int32",  "unit" : "VA",  "factor" : 10, "enabled" : 1 },
{ "idx" : 15, "loc" : 30,  "desc" : "kvar L1",   "type" : "int32",  "unit" : "var",  "factor" : 10, "enabled" : 1 },
{ "idx" : 16, "loc" : 32,  "desc" : "kvar L2",   "type" : "int32",  "unit" : "var",  "factor" : 10, "enabled" : 1 },
{ "idx" : 17, "loc" : 34,  "desc" : "kvar L3",   "type" : "int32",  "unit" : "var",  "factor" : 10, "enabled" : 1 },
{ "idx" : 18, "loc" : 36,  "desc" : "V L-N sys",   "type" : "int32",  "unit" : "Volt",  "factor" : 10, "enabled" : 1 },
{ "idx" : 19, "loc" : 38,  "desc" : "V L-L sys",   "type" : "int32",  "unit" : "Volt",  "factor" : 10, "enabled" : 1 },
{ "idx" : 20, "loc" : 40,  "desc" : "kW sys",   "type" : "int32",  "unit" : "Watt",  "factor" : 10, "enabled" : 1 },
{ "idx" : 21, "loc" : 42,  "desc" : "kVA sys",   "type" : "int32",  "unit" : "VA",  "factor" : 10, "enabled" : 1 },
{ "idx" : 22, "loc" : 44,  "desc" : "kvar sys",   "type" : "int32",  "unit" : "var",  "factor" : 10, "enabled" : 1 },
{ "idx" : 23, "loc" : 46,  "desc" : "PF L1",   "type" : "int16",  "unit" : "PF",  "factor" : 1000, "enabled" : 1 },
{ "idx" : 24, "loc" : 47,  "desc" : "PF L2",   "type" : "int16",  "unit" : "PF",  "factor" : 1000, "enabled" : 1 },
{ "idx" : 25, "loc" : 48,  "desc" : "PF L3",   "type" : "int16",  "unit" : "PF",  "factor" : 1000, "enabled" : 1 },
{ "idx" : 26, "loc" : 49,  "desc" : "PF sys",   "type" : "int16",  "unit" : "PF",  "factor" : 1000, "enabled" : 1 },
{ "idx" : 27, "loc" : 50,  "desc" : "Phase sequence",   "type" : "int16",  "unit" : "",  "factor" : 1, "enabled" : 0 },
{ "idx" : 28, "loc" : 51,  "desc" : "Hz ",   "type" : "int16",  "unit" : "Hz",  "factor" : 10, "enabled" : 1 },
{ "idx" : 29, "loc" : 52,  "desc" : "kWh (+) TOT",   "type" : "int32",  "unit" : "kWh",  "factor" : 10, "enabled" : 1 },
{ "idx" : 30, "loc" : 54,  "desc" : "Kvarh (+) TOT",   "type" : "int32",  "unit" : "kvarh",  "factor" : 10, "enabled" : 1 },
{ "idx" : 31, "loc" : 56,  "desc" : "kW dmd",   "type" : "int32",  "unit" : "Watt",  "factor" : 10, "enabled" : 0 },
{ "idx" : 32, "loc" : 58,  "desc" : "kW dmd peak",   "type" : "int32",  "unit" : "Watt",  "factor" : 10, "enabled" : 0 },
{ "idx" : 33, "loc" : 60,  "desc" : "kWh (+) PARTIAL",   "type" : "int32",  "unit" : "kWh",  "factor" : 10, "enabled" : 0 },
{ "idx" : 34, "loc" : 62,  "desc" : "Kvarh (+) PARTIAL",   "type" : "int32",  "unit" : "kvarh",  "factor" : 10, "enabled" : 0 },
{ "idx" : 35, "loc" : 64,  "desc" : "kWh (+) L1",   "type" : "int32",  "unit" : "kWh",  "factor" : 10, "enabled" : 0 },
{ "idx" : 36, "loc" : 66,  "desc" : "kWh (+) L2",   "type" : "int32",  "unit" : "kWh",  "factor" : 10, "enabled" : 0 },
{ "idx" : 37, "loc" : 68,  "desc" : "kWh (+) L3",   "type" : "int32",  "unit" : "kWh",  "factor" : 10, "enabled" : 0 },
{ "idx" : 38, "loc" : 70,  "desc" : "kWh (+) t1",   "type" : "int32",  "unit" : "kWh",  "factor" : 10, "enabled" : 0 },
{ "idx" : 39, "loc" : 72,  "desc" : "kWh (+) t2",   "type" : "int32",  "unit" : "kWh",  "factor" : 10, "enabled" : 0 },
{ "idx" : 40, "loc" : 74,  "desc" : "kWh (+) t3",   "type" : "int32",  "unit" : "NA",  "factor" : 1, "enabled" : 0 },
{ "idx" : 41, "loc" : 76,  "desc" : "kWh (+) t4",   "type" : "int32",  "unit" : "NA",  "factor" : 1, "enabled" : 0 },
{ "idx" : 42, "loc" : 78,  "desc" : "kWh (-) TOT",   "type" : "int32",  "unit" : "kWh",  "factor" : 10, "enabled" : 0 },
{ "idx" : 43, "loc" : 80,  "desc" : "kvarh (-) TOT",   "type" : "int32",  "unit" : "kvarh",  "factor" : 10, "enabled" : 0 }
]