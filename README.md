[🇫🇮Taustaa ohjelmistosta suomeksi / Background information in Finnish](docs/taustaa_fi.md)

## Idea
TO BE UPDATED...
Powerguru manages electric loads, for example water heaters or other conrollable devices/energy storages. It can heat up the boilers when then electricity is cheap, for example when you have excess solar power or nightime. It can also optimize water heating using solar energy forecast (http://www.bcdcenergia.fi/ for forecast in Finland). Current version can read RS485/Modbus enabled electric meters and DS18B20 temperatare sensors. It can also fetch Nordpool day-ahead spot prices. 

It calculates target temperatures of the heaters once in a minute and switches on/off the heater resistors to reach current target value. Dynamic target values (in Celcius) depends on current "states", which are enabled if all the criterias for the state match.   Powerguru is tested with Raspberry Pi (2)

## Data architechture

**PowerGuru** is a multithreaded Python-program running as a Linux service, see details below. Powerguru has a inbuild web-server (aiohttp) for communication with Telegraf and dashboard. Currently external devices (e.g. boilers) are controlled with Raspberry PI GPIO driven switches, but addional device interfaces, throught e.g. http API:s can be added.

[**PowerGuru Node**](https://github.com/Olli69/PowerGuru-lite) is a ESP8266 microcontroller based application providing subset of PowerGuru services. It can read Shelly 3EM energy meter, read temperature information from one DS18B20 sensor and control low-voltage switches connected to the microcontroller. Price and forecast information is fetched from PowerGuru-application as preprocessed state sets. In a basic installation a property can have one or more PowerGuru Node devices which get price and forecact information from a cloud based PowerGuru service. 

[Telegraf](https://github.com/influxdata/telegraf) is a plugin-driven server agent for collecting & reporting metrics. Telegraf gets metrics from sensors and other data sources through input plugins and forwards it to Powerguru and influxDB analytics database (optional) through output plugins. In addition to standard Telegraf plugins, custom Powerguru Telegraf input plugins (see colors in the diagram) are used. 

[InfluxDB](https://www.influxdata.com/) is an open-source time series database . [Grafana](https://grafana.com/) is an open source analytics and interactive visualization web application. Analytics of collected metrics and data is optional. A cloud based service, e.g. [InfluxDB Cloud](https://www.influxdata.com/products/influxdb-cloud/) is probobly easiest to start with. If you like to host InfluxDB locally, use other storage media than a micro SD card, which is not designed for frequent writes. 

![Data flow diagram](https://github.com/Olli69/powerguru/blob/main/docs/img/Powerguru%20data%20diagram%20with%20lite.drawio.png?raw=true)

### Telegraf - Powerguru communication
Telegraf [outputs.http plugin](https://github.com/influxdata/telegraf/blob/release-1.21/plugins/outputs/http/README.md) sends buffered metrics updates to Powerguru http interface. Powerguru calculation data series are updated to an optional InfluxDB database via Telegraf proxy service [inputs.influxdb_v2_listener](https://github.com/influxdata/telegraf/blob/release-1.21/plugins/inputs/http_listener_v2/README.md).

### Modbus energy meter
Metrics from a Modbus enabled energy meter is fetched with [Telegraf Modbus Input Plugin](https://github.com/influxdata/telegraf/blob/master/plugins/inputs/modbus/README.md). The plugin support TCP and serial line configuration. Currently Carlo Gavazzi EM340 RS meter is supported by the [Telegraf config file](settings/telegraf-powerguru.conf).

### Shelly 3EM energy meter
Currently information from Shelly EM can be read from PowerGutu Node via Wifi.

### 1-wire temperatore sensors
Temperature data from 1-wire temperature sensor DS18B20 is supported. For plugin code see [onew_telegraf_pl.py](onew_telegraf_pl.py) . PowerGuru Node support currenly only one connected sensor. 

### EntsoE
Day-ahead spot prices are fetched from [EntsoE transparency platform](https://transparency.entsoe.eu/). Next day NordPool prices are available in afternoon. For plugin code see [entsoe_telegraf_pl.py](entsoe_telegraf_pl.py) .

### BCDC Energia
BCDC Energia gives day-ahead solar-power forecast for specified locations in Finland. Data is fetched several times a day. For plugin code see [bcdc_telegraf_pl.py](bcdc_telegraf_pl.py) .

### Solar Inverters
Production data can be updated from solar (PV) inverters with a HTTP-api (e.g. Fronius Solar Api). [Telegraf HTTP input plugin](https://github.com/influxdata/telegraf/blob/release-1.21/plugins/inputs/http/README.md)

### Dashboard
<img align="right" src="https://github.com/Olli69/powerguru/blob/main/docs/img/powerguru-dashboard.png?raw=true">

Dashboard is a tiny web service showing current state of Powerguru service. You can see:
- Incoming/outgoing energy
- Currently enabled states
- Status of the channels
- Current values of variables, which are used to control statuses and channel targets
- Update status of different data from Telegraf to Powerguru




## Concept
TO BE UPDATED...
1. Main program powerguru.py listens data updates from various sources (sensors, price info, energy forecast etc) via Telegraf service. 
2. **Recalculate**-process checks, based on the data and given rules, which of defined states are enabled at the moment. Multiple states can be valid at the same time
3. Searches targets of each channel in order. E.g. target {"state" : "netsales", "upIf" : "sensor1<90"} means that if the "netsales" state is enabled (more solar production than consumption locally) then upIf formula is tested. If sensor1 value is below 90 then the channel will be up (e.g. boiler will be on) until sensor1 value reaches 90
4. Does actual switching with lineResource.setLoad . This function can also switch of the lines if there is too much load on a phase.


### States
At any time multiple states can be effective. States are enabled if "enabledIf" formula value is True. In the formula use PowerGuru variables, e.g. hhmm (current time), mmdd (current date), netEnergyInPeriod, solar24h (solar forecast for 24 hours, energyPriceSpot (current energy spot price), spotPriceRank24h (current spot price rank related to future hours). Full list of available variables you can see at the dashboard. See more details in the configuration file [settings/states.json](settings/states.json)

State parameters are defined in settings/states.json

### Channels
Currently boilers/heaters are supported or other heaters. Channel defines rules for switching channel up/down. Targets are tested in order and first matching target is used. [settings/channels.json](settings/channels.json)

![ULN2003A based Raspberry Pi switch controller hat for 12/24 DC relays](https://github.com/Olli69/powerguru/blob/main/docs/img/raspi-protohat.jpg?raw=true)
*ULN2003A based Raspberry Pi switch controller hat for 12/24 DC relays*


### Sensors
Currently only DS18B20 1-wire temperature sensors are supported. Sensors are identified by id and  defined in settings.py file.

## Installation
TO BE UPDATED...



### Files
TO BE UPDATED...
* powerguru.py - main program file. Starts from command line:  python3 powerguru.py or run as systemd service (see powerguru.service file)
* bcdc_telegraf_pl.py, entsoe_telegraf_pl.py, onew_telegraf_pl.py - custom Powerguru Telegraf input plugins
* powerguru.service - systemd service template, edit and install if you like to run powerguru as daemon
* README.md - this file, will be completed 
* setting/channels.json  
* setting/states.json  
* setting/powerguru.json  
* setting/sensors.json  
* setting/telegraf-powerguru.conf

 

### Required Python components

TO BE UPDATED...
todo: one line, updagrade
sudo apt-get install libatlas-base-dev python3-pip

sudo -H pip3 install pytz  python-dateutil twisted pymodbus influxdb entsoe-py


sudo -H pip3 install aiohttp aiohttp_sse aiohttp_session aiohttp_basicauth_middleware influxdb_client rpi.gpi
sudo -H pip3 install --upgrade entsoe-py telegraf_pyplug


Telegraf 
https://docs.influxdata.com/telegraf/v1.21/introduction/installation/ or 

sudo apt update
sudo apt upgrade
sudo apt install -y telegraf
sudo systemctl enable  telegraf
sudo systemctl start  telegraf

sudo adduser telegraf dialout # to access /dev/USB0 for ModBus

cd powerguru
#copy own version of Telegraf setup file
cp settings/telegraf-pg.conf.sample settings/telegraf-pg.conf

now get api token for e.g. influxdata.com  and edit two parameters,  token and organization, in section [[outputs.influxdb_v2]] of settings/telegraf-pg.conf . Edit also absolute paths if directory not /home/pi/powerguru
nano  settings/telegraf-pg.conf 

sudo ln -s settings/telegraf-pg.conf /etc/telegraf/telegraf.d/telegraf-pg.conf

sudo ln -s "$(pwd)/settings/telegraf-pg.conf" /etc/telegraf/telegraf.d/telegraf-pg.conf


 
.... all the other required libraries,

### Wiring
GPIOs are defined in actuators in the file settings.py. 3-phase heater uses 3 GPIOs if you want to control lines individually. In the pilot installation GPIOs draw SSR switches, which are connected to AC relays. (Maybe a LN2003 drawing a DC connector could be simpler.)

#### Wiring to a boiler, 3 phase boler has 3 of these
GPIO numbers are defined in _actuators_ list in file _settings.py_ .

    RPi GPIO  -------- 
                      SSR switch -------- AC switch  (leave to an electrician!)-------   Boiler
    RPi GND   -------- 
    
#### Electricity meter reading with Modbus
OR USE USB DONGLE... will be updated
Use raspi-config to disable serial console and enable serial port.

     RPi GPIO14 (TXD)  --------   RX               ---D+----
     RPi GPIO15 (RXD)  --------   TX    MAX3485    ---D1----    Carlo Gavazzi EM340 RS(leave to an electrician!)
     RPi 3.3V.         --------   VCC              ---GND---
     RPi GND           --------   GND
     
 
     
    
DS18B20 sensors are wired and terminated (see one-wire wiring) and how to enable one-wire https://pinout.xyz/pinout/1_wire.  Each sensor is identified by unique id and you can get recognized sensor id:s with command: `ls /sys/bus/w1/devices/`. In the beginning  all available sensors are searched in function find_thermometers and mapped to sensor codes defined in _sensors_ list defined in _settings.py_ .

    RPi GPIO 4 ----------------          --------          --- ... -----
                    |
                 4.7k ohm pull-up
                    |
    RPi 3V3    ----------------  DS18B20 --------  DS18B20 --- ... -----
    
    RPi GND    ----------------          --------          --- ... -----

Sensors should be bind to warmest part of the pipeline (outside), so that it get as hot as possible (may silicon paste and insulation outside could help). Anyway keep in minds that sensor values will be lower than real water temperature.  See mounting example https://www.openheating.org/doc/faschingbauer/thermometers.html 







