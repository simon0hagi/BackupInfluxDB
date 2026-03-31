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
   - `MAX_CONCURRENT_QUERIES`: The number of chunk queries to send to InfluxDB simultaneously. (Default: `2`).
   - `MAX_CHUNKS_PER_RUN`: The maximum number of chunks to process in a single execution. Useful for splitting backups into sections (Default: empty, runs until `END_TIME`).

## Speeding up the Backup

If you find the backup process is too slow on large datasets, try the following optimizations in your `.env` file:
1. **Increase `MAX_CONCURRENT_QUERIES`**: This uses asynchronous thread pooling to send multiple chunk requests to InfluxDB at the same time. Try bumping it from `2` to `4` or `8`. Monitor your InfluxDB server's CPU and RAM to ensure it is not getting overwhelmed.
2. **Increase `CHUNK_INTERVAL_MINUTES`**: Setting the chunk size to 1 minute means the script spends a significant amount of time just setting up HTTP requests for tiny slivers of data. Try increasing this to `10`, `60` (1 hour), or even `1440` (1 day) so InfluxDB can optimize larger disk reads.

## Pausing and Resuming

The script is fully resilient to interruptions and supports pausing:

- **Manual Pausing:** You can press `Ctrl+C` at any time while the script is running. It will finish the current chunk, save its progress to a local `.backup_state.json` file, and gracefully exit.
- **Sectioned Runs:** By configuring `MAX_CHUNKS_PER_RUN` in your `.env` file, the script will process a specific number of chunks and automatically pause, saving its state.
- **Resuming:** Whenever you run `python backup_measurement.py` again, the script will automatically detect the `.backup_state.json` file and seamlessly resume exactly where it left off, rather than starting from `START_TIME`.

*(Note: The state file is automatically deleted once the backup reaches the `END_TIME`.)*

## Usage

Once you have installed the requirements and configured your `.env` file, simply run the script:

```bash
python backup_measurement.py
```
