# State numbering - example schema
State numbers are between 0 to 65535, where 0 is undefined 

## Device specific states 1-999
Local states are not not replicated from device to device.
Currently in use:

| State      | Description  |
| ------------- |------------- |
| 1 | always on  |
| 100 | hour 00, local time 00:00-00:59 |
| 101 | hour 01|
| 102...122 | hour 02... hour |
| 123 | hour 23, local time|
| 130 RFU| päiväsähkö, daytime 07-22:, every day|
| 131 RFU| yösähkö, 22-07, every day|
| 140 RFU| kausisähkö talvipäivä, Nov 1- Mar 31 07-22, Mon-Sat|
| 141 RFU| kausisähkö, other time|



## Property specific states 1000-9999
Property specific states can depend on local conditions, e.g. local power production/consumption and net purchase from grid within netting period, which are sensored or metered locally. Property specific states can be replicated from central instance of the property to local PowerGuru Lite instances.

| State      | Description  |
| ------------- |------------- |
| 1001 | buying, more production than purchase in current netting period  |
| 1005 | selling, more production than purchase in current netting period|
| 1006 | selling, before solar noon|
| 1007 | selling, after solar noon|
| 1010 | extra production, more production than defined base load|
| 1011 | extra production, before solar noon|
| 1012 | extra production, after solar noon|
| 19XX | energy forecast from BCDC Energia http://www.bcdcenergia.fi/, need refinement|
| 1910 | dark day coming|
| 1920 | sunny day coming|



## Price area specific states 10000-65535
Price area specific states  depend on spot prices on the specific price area. FI-Finland is one price are, e.g. Norway and Sweden are divided to several price areas. These states can be defined and refined in local PowerGuru instance or states can be loaded from a cloud instance. Day-ahead price data is loaded from EntsoE transparency platform https://transparency.entsoe.eu/. 

- 10115 - morning 7-10
- 10120 - evening 18-20 

- 11000 - spot pricing
- 11010 - spot very low < 2 c/kWh
- 11012 - spot low, <4 c/kWh
- 11014 - spot moderate < 6 c/kWh
- 11020 - spot pretty expensive > 10 c/kWh
- 11021 - spot expensive > 15 c/kWh
- 11022 - spot very expensive >30 c/kWh

- 11100 - best spot price ranks in various windows 
- 11110 - 6h window
- 11111 - cheapest 1 h in 6 h
- 11112 - cheapest 2 h in 6 h
- 11113 - cheapest 3 h in 6 h

- 11120 - 12h window
- 11130 - 18h window

- 11140 - 24h window
- 11141 - cheapest 1 h in 24 h
- 11142 - cheapest 2 h in 24 h
- 11143 - cheapest 3 h in 24 h
- 11144 - cheapest 4 h in 24 h
- 11145 - cheapest 5 h in 24 h
- 11146 - cheapest 6 h in 24 h
- 11150 - 24h window , spot < 4
- 11151 - cheapest 1 h in 24 h, <4 c/kWh
- 11152 - cheapest 2 h in 24 h, <4 c/kWh
- 11153 - cheapest 3 h in 24 h, <4 c/kWh
- 11154 - cheapest 4 h in 24 h, <4 c/kWh
- 11155 - cheapest 5 h in 24 h, <4 c/kWh
- 11156 - cheapest 6 h in 24 h, <4 c/kWh






