import os
import sys
import time
from datetime import datetime, timedelta, timezone
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError, InfluxDBServerError

def parse_iso_time(time_str):
    # Handle 'Z' suffix for UTC which fromisoformat might not handle in older Pythons
    if time_str.endswith('Z'):
        time_str = time_str[:-1] + '+00:00'
    return datetime.fromisoformat(time_str)

def get_env_or_die(var_name):
    val = os.environ.get(var_name)
    if not val:
        print(f"Error: Environment variable {var_name} is required.")
        sys.exit(1)
    return val

def main():
    # Read environment variables
    host = os.environ.get('INFLUXDB_HOST', 'localhost')
    port = int(os.environ.get('INFLUXDB_PORT', '8086'))
    user = os.environ.get('INFLUXDB_USER', '')
    password = os.environ.get('INFLUXDB_PASSWORD', '')
    database = get_env_or_die('INFLUXDB_DATABASE')

    source_measurement = get_env_or_die('SOURCE_MEASUREMENT')
    target_measurement = get_env_or_die('TARGET_MEASUREMENT')

    start_time_str = get_env_or_die('START_TIME')
    end_time_str = get_env_or_die('END_TIME')

    try:
        chunk_interval_minutes = int(os.environ.get('CHUNK_INTERVAL_MINUTES', '1'))
    except ValueError:
        print("Error: CHUNK_INTERVAL_MINUTES must be an integer.")
        sys.exit(1)

    try:
        start_time = parse_iso_time(start_time_str)
        end_time = parse_iso_time(end_time_str)
    except ValueError as e:
        print(f"Error parsing start or end time: {e}")
        print("Expected format: YYYY-MM-DDTHH:MM:SSZ (e.g. 2023-01-01T00:00:00Z)")
        sys.exit(1)

    if start_time >= end_time:
        print("Error: START_TIME must be before END_TIME.")
        sys.exit(1)

    # Initialize InfluxDB Client
    client = InfluxDBClient(host=host, port=port, username=user, password=password, database=database)

    print(f"Connecting to InfluxDB at {host}:{port}, database '{database}'...")
    try:
        # Test connection
        client.ping()
        print("Successfully connected to InfluxDB.")
    except Exception as e:
        print(f"Failed to connect to InfluxDB: {e}")
        sys.exit(1)

    print(f"Copying data from '{source_measurement}' to '{target_measurement}'")
    print(f"Time range: {start_time.isoformat()} to {end_time.isoformat()}")
    print(f"Chunk interval: {chunk_interval_minutes} minute(s)")

    current_time = start_time
    chunk_delta = timedelta(minutes=chunk_interval_minutes)

    total_chunks = int(((end_time - start_time).total_seconds() / 60.0) / chunk_interval_minutes)
    if total_chunks == 0:
        total_chunks = 1

    chunk_count = 0

    while current_time < end_time:
        next_time = current_time + chunk_delta
        if next_time > end_time:
            next_time = end_time

        # Format for InfluxDB WHERE clause (RFC3339)
        # InfluxDB needs 'YYYY-MM-DDTHH:MM:SSZ' format or nanoseconds.
        # By using isoformat(), we get a valid string, but let's replace +00:00 with Z for standard Influx compat
        t1 = current_time.isoformat().replace('+00:00', 'Z')
        t2 = next_time.isoformat().replace('+00:00', 'Z')

        query = f'SELECT * INTO "{target_measurement}" FROM "{source_measurement}" WHERE time >= \'{t1}\' AND time < \'{t2}\' GROUP BY *'

        chunk_count += 1
        print(f"[{chunk_count}/{total_chunks}] Executing query for range: {t1} -> {t2}")

        max_retries = 3
        retry_delay = 2 # seconds
        success = False

        for attempt in range(1, max_retries + 1):
            try:
                # Execute the query (requires POST for INTO queries)
                result = client.query(query, method='POST')
                success = True
                break
            except (InfluxDBServerError, InfluxDBClientError) as e:
                print(f"  Attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    print(f"  Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2 # Exponential backoff
            except Exception as e:
                print(f"  Unexpected error during query execution: {e}")
                if attempt < max_retries:
                    print(f"  Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2 # Exponential backoff

        if not success:
            print(f"Failed to process chunk {t1} -> {t2} after {max_retries} attempts.")
            print("Aborting to ensure no data is missing. Please investigate and resume from this chunk.")
            sys.exit(1)

        current_time = next_time

    print("\nBackup completed successfully!")

if __name__ == "__main__":
    main()
