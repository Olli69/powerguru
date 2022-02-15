# PowerGuru variables

## Calendar based variables

| Variable      | Description  |
| ------------- |------------- |
| hhmm | Current as hour and minute in local time (24 h clock), string, e.g. '1335'  |
| mmdd | Current month and day , string, e.g. '0215' (February 15th) |

## Sensor and meter based variables

Numeric value of (temperaturu) sensor where variable name equals sensor name, e.g. sensor1	23.1

| Variable      | Description  |
| ------------- |------------- |
| sensor1 | Numeric sensor value  of sensor 1, typically temperature sensor.,  |
| sensor2,.. | |
| netEnergyInPeriod| Incoming net energy during current period (hour) (Wh).  |
| netPowerInPeriod | Average incoming net power during curretn period (W) |


## Day-ahead price based variables
Variable values are generated based day-ahead prices from EntsoE transparency platform https://transparency.entsoe.eu/ . Prices are price ares dependant, e.g. Finland is one price area, code FI.

The aay-ahead variables are available on PowerGuru only, not PowerGuru lite.  

| Variable      | Description  |
| ------------- |------------- |
| energyPriceSpot | Current energy price, c/kWh |
| spotPriceRank6h | Rank of current price in 6 hour window. For example 1 means that current price is cheapest within 6 hours (now and next 5) |
| spotPriceRank12h | Rank of current price in 12 hour window. |
| spotPriceRank18h | Rank of current price in 18 hour window. |
| spotPriceRank24h | Rank of current price in 24 hour window. |

## Solar forecast based variables

Location based values based on data from BCDC Energia http://www.bcdcenergia.fi/ .

| Variable      | Description  |
| ------------- |------------- |
| solar6h       | Forecasted solar energy for coming 6 hours |
| solar12h      | Forecasted solar energy for coming 12 hours | 
| solar18h      | Forecasted solar energy for coming 18 hours |
| solar24h      | Forecasted solar energy for coming 24 hours |



