import os
import sys
import time
import math
import logging
from datetime import datetime, timedelta, timezone
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError, InfluxDBServerError
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def parse_iso_time(time_str):
    # Handle 'Z' suffix for UTC which fromisoformat might not handle in older Pythons
    if time_str.endswith('Z'):
        time_str = time_str[:-1] + '+00:00'
    return datetime.fromisoformat(time_str)

def get_env_or_die(var_name):
    val = os.environ.get(var_name)
    if not val:
        logger.error(f"Environment variable {var_name} is required in the .env file.")
        sys.exit(1)
    return val

def count_measurement_points(client, database, measurement, start_time, end_time):
    """Helper to count points in a measurement for a given time range."""
    t1 = start_time.isoformat().replace('+00:00', 'Z')
    t2 = end_time.isoformat().replace('+00:00', 'Z')

    # We fully qualify the measurement to handle target database queries
    query = f'SELECT COUNT(*) FROM "{database}".."{measurement}" WHERE time >= \'{t1}\' AND time < \'{t2}\''
    try:
        result = client.query(query, method='GET')
        points = list(result.get_points())
        if points:
            # The count function returns the count for all fields, we just grab the first one
            first_field = list(points[0].keys())[-1]
            return points[0][first_field]
        return 0
    except Exception as e:
        logger.warning(f"Could not count points for '{database}'.'{measurement}': {e}")
        return None

def main():
    # Load configuration from .env file
    load_dotenv()

    # Read environment variables
    host = os.environ.get('INFLUXDB_HOST', 'localhost')
    port = int(os.environ.get('INFLUXDB_PORT', '8086'))
    user = os.environ.get('INFLUXDB_USER', '')
    password = os.environ.get('INFLUXDB_PASSWORD', '')
    database = get_env_or_die('INFLUXDB_DATABASE')
    target_database = os.environ.get('TARGET_DATABASE', database)

    source_measurement = get_env_or_die('SOURCE_MEASUREMENT')
    target_measurement = get_env_or_die('TARGET_MEASUREMENT')

    start_time_str = get_env_or_die('START_TIME')
    end_time_str = get_env_or_die('END_TIME')

    try:
        chunk_interval_minutes = int(os.environ.get('CHUNK_INTERVAL_MINUTES', '1'))
    except ValueError:
        logger.error("CHUNK_INTERVAL_MINUTES must be an integer.")
        sys.exit(1)

    try:
        start_time = parse_iso_time(start_time_str)
        end_time = parse_iso_time(end_time_str)
    except ValueError as e:
        logger.error(f"Error parsing start or end time: {e}")
        logger.error("Expected format: YYYY-MM-DDTHH:MM:SSZ (e.g. 2023-01-01T00:00:00Z)")
        sys.exit(1)

    if start_time >= end_time:
        logger.error("START_TIME must be before END_TIME.")
        sys.exit(1)

    # Initialize InfluxDB Client
    client = InfluxDBClient(host=host, port=port, username=user, password=password, database=database)

    logger.info(f"Connecting to InfluxDB at {host}:{port}, database '{database}'...")
    try:
        # Test connection
        client.ping()
        logger.info("Successfully connected to InfluxDB.")

        # Verify target database exists if it's different
        if target_database != database:
            dbs = client.get_list_database()
            if not any(db['name'] == target_database for db in dbs):
                logger.error(f"Target database '{target_database}' does not exist. Please create it first.")
                sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to connect to InfluxDB or verify databases: {e}")
        sys.exit(1)

    logger.info("--- Configuration Summary ---")
    logger.info(f"Source: Database '{database}', Measurement '{source_measurement}'")
    logger.info(f"Target: Database '{target_database}', Measurement '{target_measurement}'")
    logger.info(f"Time Range: {start_time.isoformat()} to {end_time.isoformat()}")
    logger.info(f"Chunk Interval: {chunk_interval_minutes} minute(s)")
    logger.info("-----------------------------")

    # Analyze data before starting
    logger.info("Analyzing source measurement data...")

    # Show an example line
    example_query = f'SELECT * FROM "{database}".."{source_measurement}" LIMIT 1'
    try:
        example_result = client.query(example_query, method='GET')
        points = list(example_result.get_points())
        if points:
            logger.info("Example data point from source:")
            logger.info(points[0])
        else:
            logger.info("Source measurement is empty or has no data yet.")
    except Exception as e:
        logger.warning(f"Could not fetch example data point: {e}")

    initial_source_count = count_measurement_points(client, database, source_measurement, start_time, end_time)

    if initial_source_count is not None:
        if initial_source_count == 0:
            logger.warning(f"No points found in the source measurement '{source_measurement}' for the specified time range. Exiting.")
            sys.exit(0)
        else:
            logger.info(f"Found approximately {initial_source_count:,} points to copy.")
    else:
        logger.info("Could not determine point count. Proceeding anyway.")

    current_time = start_time
    chunk_delta = timedelta(minutes=chunk_interval_minutes)

    total_chunks = math.ceil(((end_time - start_time).total_seconds() / 60.0) / chunk_interval_minutes)
    if total_chunks == 0:
        total_chunks = 1

    chunk_count = 0
    total_points_written = 0

    logger.info(f"Starting backup process. Total chunks to process: {total_chunks}")

    while current_time < end_time:
        next_time = current_time + chunk_delta
        if next_time > end_time:
            next_time = end_time

        # Format for InfluxDB WHERE clause (RFC3339)
        # InfluxDB needs 'YYYY-MM-DDTHH:MM:SSZ' format or nanoseconds.
        # By using isoformat(), we get a valid string, but let's replace +00:00 with Z for standard Influx compat
        t1 = current_time.isoformat().replace('+00:00', 'Z')
        t2 = next_time.isoformat().replace('+00:00', 'Z')

        # Fully qualify target measurement to allow cross-database copying.
        # Format: "database"."retention_policy"."measurement"
        # We leave the retention policy empty to use the database's default retention policy.
        qualified_target = f'"{target_database}".."{target_measurement}"'

        query = f'SELECT * INTO {qualified_target} FROM "{source_measurement}" WHERE time >= \'{t1}\' AND time < \'{t2}\' GROUP BY *'

        chunk_count += 1

        max_retries = 3
        retry_delay = 2 # seconds
        success = False
        points_in_chunk = 0

        for attempt in range(1, max_retries + 1):
            try:
                # Execute the query (requires POST for INTO queries)
                result = client.query(query, method='POST')

                # InfluxDB SELECT INTO returns a single series with a "written" field
                # e.g. [{'time': '1970-01-01T00:00:00Z', 'written': 150}]
                written_points = list(result.get_points())
                if written_points and 'written' in written_points[0]:
                    points_in_chunk = written_points[0]['written']

                total_points_written += points_in_chunk
                success = True
                break
            except (InfluxDBServerError, InfluxDBClientError) as e:
                logger.warning(f"Attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2 # Exponential backoff
            except Exception as e:
                logger.error(f"Unexpected error during query execution: {e}")
                if attempt < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2 # Exponential backoff

        if not success:
            logger.error(f"Failed to process chunk {t1} -> {t2} after {max_retries} attempts.")
            logger.error("Aborting to ensure no data is missing. Please investigate and resume from this chunk.")
            sys.exit(1)

        # Log progress periodically (e.g. every 5% of chunks, or at least every 10 chunks if few chunks)
        # Always log the first and last chunk
        log_interval = max(1, int(total_chunks * 0.05))
        if chunk_count == 1 or chunk_count == total_chunks or chunk_count % log_interval == 0:
            percentage = (chunk_count / total_chunks) * 100

            if initial_source_count is not None and initial_source_count > 0:
                points_remaining = max(0, initial_source_count - total_points_written)
                logger.info(f"Progress: [{chunk_count}/{total_chunks}] chunks ({percentage:.1f}%) | "
                            f"Copied {total_points_written:,} points | Remaining: ~{points_remaining:,}")
            else:
                logger.info(f"Progress: [{chunk_count}/{total_chunks}] chunks ({percentage:.1f}%) | "
                            f"Copied {total_points_written:,} points")

        current_time = next_time

    logger.info("Backup process finished!")
    logger.info(f"Total points written across all chunks: {total_points_written:,}")

    # Final verification
    if initial_source_count is not None and initial_source_count > 0:
        logger.info("Verifying copied data...")
        final_target_count = count_measurement_points(client, target_database, target_measurement, start_time, end_time)

        if final_target_count is not None:
            logger.info("--- Final Summary ---")
            logger.info(f"Source points counted: {initial_source_count:,}")
            logger.info(f"Target points written: {final_target_count:,}")

            if final_target_count >= initial_source_count:
                logger.info("Verification Successful: Target contains all expected points.")
            else:
                logger.warning(f"Verification Mismatch: Target is missing {initial_source_count - final_target_count:,} points!")
        else:
             logger.info("Data was copied, but could not automatically verify target point count.")

if __name__ == "__main__":
    main()
