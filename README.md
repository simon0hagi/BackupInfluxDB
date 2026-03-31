# InfluxDB Measurement Backup

This script copies data from one measurement to another within an InfluxDB (version 1.8.x) database.
It supports copying data within the same database, or backing it up to a completely different database on the same server.
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

Configuration is managed via a `.env` file in the project directory. This approach keeps your settings local and prevents the need to export global environment variables.

1. Copy the provided example configuration file:
   ```bash
   cp .env.example .env
   ```

2. Open `.env` in a text editor and fill in your specific details:

   **Required:**
   - `INFLUXDB_DATABASE`: The name of the source database.
   - `SOURCE_MEASUREMENT`: The name of the measurement you want to copy from.
   - `TARGET_MEASUREMENT`: The name of the measurement you want to copy to.
   - `START_TIME`: The beginning of the time range to copy, in ISO 8601 format (e.g., `2023-01-01T00:00:00Z`).
   - `END_TIME`: The end of the time range to copy, in ISO 8601 format (e.g., `2023-02-01T00:00:00Z`).

   **Optional:**
   - `TARGET_DATABASE`: The database to write the backup to (Default: same as `INFLUXDB_DATABASE`). **Note: This database must already exist.**
   - `INFLUXDB_HOST`: Hostname of the InfluxDB server (Default: `localhost`).
   - `INFLUXDB_PORT`: Port of the InfluxDB server (Default: `8086`).
   - `INFLUXDB_USER`: Username for InfluxDB authentication (Default: empty).
   - `INFLUXDB_PASSWORD`: Password for InfluxDB authentication (Default: empty).
   - `CHUNK_INTERVAL_MINUTES`: How many minutes of data to copy per database query (Default: `1`).

## Usage

Once you have installed the requirements and configured your `.env` file, simply run the script:

```bash
python backup_measurement.py
```
