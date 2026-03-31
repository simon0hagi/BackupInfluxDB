# InfluxDB Measurement Backup

This script copies data from one measurement to another within the same InfluxDB (version 1.8.x) database.
It uses InfluxDB's native `SELECT ... INTO ...` feature for maximum efficiency, processing the data in small chunks to avoid memory or timeout issues with large datasets.

## Requirements
- Python 3.7+
- InfluxDB 1.8.x (Target database)

## Installation
Install the required dependencies using `pip`:
```bash
pip install -r requirements.txt
```

## Configuration

Configuration is done via environment variables.

### Required
- `INFLUXDB_DATABASE`: The name of the database.
- `SOURCE_MEASUREMENT`: The name of the measurement you want to copy from.
- `TARGET_MEASUREMENT`: The name of the measurement you want to copy to.
- `START_TIME`: The beginning of the time range to copy, in ISO 8601 format (e.g., `2023-01-01T00:00:00Z`).
- `END_TIME`: The end of the time range to copy, in ISO 8601 format (e.g., `2023-02-01T00:00:00Z`).

### Optional
- `INFLUXDB_HOST`: Hostname of the InfluxDB server (Default: `localhost`).
- `INFLUXDB_PORT`: Port of the InfluxDB server (Default: `8086`).
- `INFLUXDB_USER`: Username for InfluxDB authentication (Default: empty).
- `INFLUXDB_PASSWORD`: Password for InfluxDB authentication (Default: empty).
- `CHUNK_INTERVAL_MINUTES`: How many minutes of data to copy per database query (Default: `1`).

## Example Usage

### On Linux/macOS
```bash
export INFLUXDB_HOST="localhost"
export INFLUXDB_PORT="8086"
export INFLUXDB_DATABASE="my_db"
export SOURCE_MEASUREMENT="measured_v3"
export TARGET_MEASUREMENT="measured_v3_backup"
export START_TIME="2023-01-01T00:00:00Z"
export END_TIME="2023-02-01T00:00:00Z"
export CHUNK_INTERVAL_MINUTES="1"

python backup_measurement.py
```
