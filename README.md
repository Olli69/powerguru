## A few words in Finnish
Mikäli olet kiinnostunut saamaan lisätietoa tästä voit lähettää tekijälle sähköpostia olli@rinne.fi. Keskustelua voisi tietysti käydä myös FB:n Aurinkoenergia-ryhmässä, josta ajatus tämän julkaisusta tuli. Voit myös halutessassi avata issuen suomeksi. Käytännön syistä dokumentaatio on kuitenkin ainakin toistaiseksi vain englanniksi.

Ohjelma getfcstandprices.py hakee paikallisen aurinkoenergiaennusteen ja Nordpoolin day-ahead SPOT-tuntihinnat (vaatii ilmaisen API-avaimen). SPOT-hintoja ei vielä käytetä ohjauksessa, mutta ominaisuus on melko helppo lisätä ja tekijä mielellään on mukana tässä. Käytännössä hintaohjauksen voisi tehdä lisäämällä esimerkiksi ehtokriteereihin (laajentamalla funtiota check_conditions ) totuusarvomuuttujat  (boolean) spotlow5 (true, jos kuluva tunti kuuluu 5 halvimman tunnin joukkoon), jne.spotlow10, spothigh10, spothigh5 . Ehtoihin voisi tietysti myös lisätä myös absoluuttiseen hintaan viittaavat spotpricebelow and spotpriceabove-attribuutit, jolloin esim. "spotpricebelow" : 3.0 on voimassa kun SPOT-hinta on alle 3 c/kWh. jne .

## Idea
Powerguru manages electric loads (especially 1 or 3 phase water heaters). It can heat up the boilers when then electricity is cheap, for example when you have excess solar power or nightime. It can also optimize water heating using solar energy forecast (http://www.bcdcenergia.fi/ for forecast in Finland). Current version can read RS485/Modbus enables electric meters and DS18B20 temperatare sensors. It can also fetch Nordpool day-ahead spot prices. 

It calculates target temperatures of the heaters once in a minute and switches on/off the heater resistors to reach current target value. Dynamic target values (in Celcius) depends on current "conditions", which are enabled if all the criterias for the condition match.   Powerguru is tested with Raspberry Pi (2)

## Concept
Main program powerguru.py runs function doWork and does following once in a minute (parameter READ_INTERVAL) in 
1. reads ModBus capable electic meter and temperature sensors .
2. Insert new values to InfluxDB
3. Checks which conditions are valid in that moment. Multiple conditions can be valid at the same time,
4. Searches targets of each actuator in order. E.g. target {"condition" : "sun", "sensor" : "b2out", "valueabove": 80} means that if sun (net sales) condition is true, sensor b2out target value if 80 C. If condition "sun" is true but sensor "b2out" temperature is below 80 then the system tries to switch on more lines (if possible). If temperature is above 80, it can switch of the lines (of that actuator).
5. Does actual switching with lineResource.setLoad . This function can also switch of the lines if there is too much load on a phase.
### Conditions
At any time multiple conditions can be effective. Conditions are enabled based on one or more criterias, which should be fulfilled:
- current time, criteria defined with _starttime_ (e.g. "04:00:00") and _endtime_ (e.g. "07:00:00)
- current date, defined with parameters _dayfirst_ and _daylast_  -  format MM-DD,  e.g. "02-15" is February 15
- solar forecast, attributes _solar12above_ and  _solar12below_ are defined. _"solar12above" : 5.0_ means that expected cumulative solar power within next 12 h should be 5kWh or more (with 1 kWp panels)
- in the future there could be criterias for price-based selection, e.g. _spotpricebelow_
Condition parameter are defined in settings.py file.
### Actuators
Currently only (1 or 3 line) boilers/heaters are supported. Actuator defines GPIOs of all phases (1 or 3) and target values (temperatures) in different conditions. Targets are tested in order and first matching target is used. Actuators are defined in settings.py file.
### Sensors
Currently only DS18B20 1-wire temperature sensors are supported. Sensors are identified by id and  defined in settings.py file.

## Installation

### Files
* settings.py - parameter file, use settings-example.py as a template
* powerguru.py - main program file. Starts from command line:  python3 powerguru.py or run as systemd service (see powerguru.service file)
* powerguru.service - systemd service template, edit and install if you like to run powerguru as daemon
* README.md - this file, will be completed (if anybody is interested :) )
* getfcstandprices.py - reads NordPool prices and BCDC solar forecast. You can schedule it with crontab, e.g. once in 4 hours:15 */4 * * * /usr/bin/python3.7 /home/pi/powerguru/getfcstandprices.py
 

### Required Python components


todo: one line, updagrade
sudo apt-get install libatlas-base-dev python3-pip

sudo -H pip3 install pytz  python-dateutil twisted pymodbus influxdb entsoe-py

 
.... all the other required libraries,

### Wiring
GPIOs are defined in actuators in the file settings.py. 3-phase heater uses 3 GPIOs if you want to control lines individually. In the pilot installation GPIOs draw SSR switches, which are connected to AC relays. (Maybe a LN2003 drawing a DC connector could be simpler.)

#### Wiring to a boiler, 3 phase boler has 3 of these
GPIO numbers are defined in _actuators_ list in file _settings.py_ .

    RPi GPIO  -------- 
                      SSR switch -------- AC switch  (leave to an electrician!)-------   Boiler
    RPi GND   -------- 
    
#### Electricity meter reading with Modbus
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



## Credits
If try to check out where the ModBus code was copied from...






