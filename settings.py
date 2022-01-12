
import os

basicInfo = {"maxLoadPerPhaseA" : 50.0 #allow max this current per phase, if higher try to cut load
            } 


timeZoneLocal = "Europe/Helsinki"
nettingPeriodMinutes = 60 # 0-no netting, 15 - 15 min period (coming, 60 - 1 hour (current somewhere in Finland )


def replace_path_from_script(file_name):
    if file_name[0]==".":
        return os.path.dirname(__file__) + file_name[1:]
    else:
        return file_name
    
dayahead_file_name = "./data/dayahead.json"
forecastpv_file_name = "./data/forecastpv.json"
onewire_settings_filename =  "./settings/onewire.json"
conditions_filename =  "./settings/conditions.json"
channels_filename =  "./settings/channels.json"
volts_per_phase = 230

#influxDb variables
influxType = 'cloud' # local, no

 # You can generate an API token from the "API Tokens Tab" in the UI
ifUrl =  "https://europe-west1-1.gcp.cloud2.influxdata.com"
ifToken = "HkJ2wTuiu4Sy13-rTrQ1DmTyBmobD1_kSr3tjCMaK7vGsyeIDSanNG3CMoXU9C7lHgfEdfsBrkOjqn0jFcWz5w=="
ifOrg = "olli@feelthenature.fi"
ifBucket = "powerguru"

    
ifHost = '127.0.01' # InfluxDB host name
ifPort = 8086               # InfluxDB port
ifDatabase ='powerguru'         # InfluxDB database name
ifUsername= 'powerguru_admin'         # InfluxDB
ifPassword= 'change_this'      # InfluxDB password
ifssl=False                 # InfluxDB is ssl used
ifVerify_ssl=False          # InfluxDB is ssl certificate verified
ifTimeout=10                # InfluxDB connection timeout


bcdcenergiaLocation = "Salo" # check you nearest location at http://www.bcdcenergia.fi/


#Entso EU API, request this key from EntsoEU web site
EntsoEUAPIToken = '41c76142-eaab-4bc2-9dc4-5215017e4f6b'
NordPoolPriceArea = 'FI'

# Pricing parameters, Finnish pricing and tax model
"""
transferPriceDay = 3.59     # transfer price c/kWh, daytime,  YOUR PRICE HERE
transferPriceNight = 2.21   # transfer price c/kWh, nighttime,  YOUR PRICE HERE
energyPriceDay = 6.00       # energy price c/kWh, daytime , YOUR PRICE HERE
energyPriceNight = 4.50     # energy price c/kWh, nighttime, , YOUR PRICE HERE     
electricityTax =2.253       # electricity price c/kWh, Finnish taxation model
spotMarginPurchase = 0.24   # if SPOT agreement in purchase, your margin to the seller 
spotMarginSales = 0.24      # if SPOT agreement in sales, your margin to the buyer 
vatFactor = 1.24            # VAT factor, 24% -> 1.24
"""
daytimeStarts = "07:00:00"
daytimeEnds = "22:00:00"





