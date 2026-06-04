import os
import sys
import time
import math
import json
import logging
import asyncio
import aiohttp
from aioinflux import InfluxDBClient as AsyncInfluxDBClient
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd

from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError, InfluxDBServerError
from dotenv import load_dotenv

from constants import TAGLIST_PATH
from file_loader import get_uid_for_tagset

env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

#uids = get_uid_for_tagset(TAGLIST_PATH)

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
            # The count function returns the count for all fields, we grab the first non-time field
            for key, value in points[0].items():
                if key != 'time':
                    return value
        return 0
    except Exception as e:
        logger.warning(f"Could not count points for '{database}'.'{measurement}': {e}")
        return None

STATE_FILE = ".backup_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not read state file {STATE_FILE}: {e}")
    return None

def save_state(state_data):
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state_data, f, indent=4)
    except Exception as e:
        logger.warning(f"Could not save state to {STATE_FILE}: {e}")

def clear_state():
    if os.path.exists(STATE_FILE):
        try:
            os.remove(STATE_FILE)
            logger.info("Cleared backup state file.")
        except Exception as e:
            logger.warning(f"Could not clear state file {STATE_FILE}: {e}")

async def async_main():
    # Load configuration from .env file
    load_dotenv()

    # Read environment variables
    source_host = os.environ.get('SOURCE_INFLUXDB_HOST')
    target_host = os.environ.get('TARGET_INFLUXDB_HOST')

    source_port = int(os.environ.get('SOURCE_INFLUXDB_PORT'))
    target_port = int(os.environ.get('TARGET_INFLUXDB_PORT'))

    source_token = os.environ.get('SOURCE_INFLUXDB_TOKEN', '')
    target_token = os.environ.get('TARGET_INFLUXDB_TOKEN', '')

    source_database = get_env_or_die('SOURCE_DATABASE')
    target_database = os.environ.get('TARGET_DATABASE')

    source_measurement = get_env_or_die('SOURCE_MEASUREMENT')
    target_measurement = get_env_or_die('TARGET_MEASUREMENT')

    taglist_file = Path.cwd().parent / "config" / get_env_or_die('TAGLIST_FILE')

    start_time_str = get_env_or_die('START_TIME')
    end_time_str = get_env_or_die('END_TIME')

    try:
        chunk_interval_minutes = int(os.environ.get('CHUNK_INTERVAL_MINUTES', '1'))
    except ValueError:
        logger.error("CHUNK_INTERVAL_MINUTES must be an integer.")
        sys.exit(1)

    try:
        max_workers_env = os.environ.get('MAX_CONCURRENT_QUERIES', '2')
        max_concurrent_queries = int(max_workers_env)
        if max_concurrent_queries < 1:
            max_concurrent_queries = 1
    except ValueError:
        logger.error("MAX_CONCURRENT_QUERIES must be a positive integer.")
        sys.exit(1)

    try:
        max_chunks_env = os.environ.get('MAX_CHUNKS_PER_RUN', '')
        max_chunks_per_run = int(max_chunks_env) if max_chunks_env else None
    except ValueError:
        logger.error("MAX_CHUNKS_PER_RUN must be an integer.")
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

    #Build inverted index for UIDs for quick lookup in taglist
    logger.info(f"Loading tags from {taglist_file} and building UID index...")
    uid_index = get_uid_for_tagset(taglist_file)
    logger.info(f"Built UID index with {len(uid_index)} entries.")


    # Initialize InfluxDB Client
    source_client = InfluxDBClient(host=source_host, port=source_port, database=source_database, ssl=True, verify_ssl=True, headers={"Authorization": f"Bearer {source_token}"})
    target_client = InfluxDBClient(host=target_host, port=target_port, database=target_database, ssl=True, verify_ssl=True, headers={"Authorization": f"Bearer {target_token}"})

    # Create async clients
    async_source_client = AsyncInfluxDBClient(host=source_host, port=source_port, db=source_database, ssl=True, headers={"Authorization": f"Bearer {source_token}"})
    async_target_client = AsyncInfluxDBClient(host=target_host, port=target_port, db=target_database, ssl=True, headers={"Authorization": f"Bearer {target_token}"})


    # test source connection
    logger.info(f"Connecting to InfluxDB at {source_host}:{source_port}, source_database '{source_database}'...")
    try:
        source_client.ping()
        logger.info("Successfully connected to source InfluxDB.")
    except Exception as e:
        logger.error(f"Failed to connect to InfluxDB or verify databases: {e}")
        sys.exit(1)

    # test target connection
    logger.info(f"Connecting to InfluxDB at {target_host}:{target_port}, target_database '{target_database}'...")
    try:
        target_client.ping()
        logger.info("Successfully connected to target InfluxDB.")
    except Exception as e:
        logger.error(f"Failed to connect to InfluxDB or verify databases: {e}")
        sys.exit(1)

    logger.info("--- Configuration Summary ---")
    logger.info(f"Source: Database '{source_database}', Measurement '{source_measurement}'")
    logger.info(f"Target: Database '{target_database}', Measurement '{target_measurement}'")
    logger.info(f"Time Range: {start_time.isoformat()} to {end_time.isoformat()}")
    logger.info(f"Chunk Interval: {chunk_interval_minutes} minute(s)")
    logger.info(f"Max Concurrent Queries: {max_concurrent_queries}")
    logger.info(f"Max Chunks Per Run: {max_chunks_per_run if max_chunks_per_run is not None else 'No limit'}")
    logger.info("-----------------------------")

    # Analyze data before starting
    logger.info("Analyzing source measurement data...")

    # Show an example line
    example_query = f'SELECT * FROM "{source_database}".."{source_measurement}" LIMIT 1'
    try:
        example_result = source_client.query(example_query, method='GET')
        points = list(example_result.get_points())
        if points:
            logger.info("Example data point from source:")
            logger.info(points[0])
        else:
            logger.info("Source measurement is empty or has no data yet.")
    except Exception as e:
        logger.warning(f"Could not fetch example data point: {e}")

    initial_source_count = count_measurement_points(source_client, source_database, source_measurement, start_time, end_time)

    if initial_source_count is not None:
        if initial_source_count == 0:
            logger.warning(f"No points found in the source measurement '{source_measurement}' for the specified time range. Exiting.")
            sys.exit(0)
        else:
            logger.info(f"Found approximately {initial_source_count:,} points to copy.")
    else:
        logger.info("Could not determine point count. Proceeding anyway.")

    # Check for existing state
    current_time = start_time
    chunk_count = 0
    total_points_written = 0

    state = load_state()
    if state:
        # Verify the state matches our current config to avoid resuming a different backup
        if (state.get('source_database') == source_database and
            state.get('source_measurement') == source_measurement and
            state.get('target_measurement') == target_measurement):

            resume_time = parse_iso_time(state['current_time'])
            if start_time <= resume_time < end_time:
                logger.info(f"Resuming previous backup from {resume_time.isoformat()}...")
                current_time = resume_time
                chunk_count = state.get('chunk_count', 0)
                total_points_written = state.get('total_points_written', 0)
            else:
                logger.info("Found state file, but its time is outside the current range. Starting fresh.")
                clear_state()
        else:
            logger.info("Found state file for a different backup configuration. Starting fresh.")
            clear_state()

    chunk_delta = timedelta(minutes=chunk_interval_minutes)

    # Recalculate chunks based on the original start time so the percentage makes sense
    total_chunks = math.ceil(((end_time - start_time).total_seconds() / 60.0) / chunk_interval_minutes)
    if total_chunks == 0:
        total_chunks = 1

    logger.info(f"Starting backup process. Total chunks in range: {total_chunks}")

    chunks_processed_this_run = 0
    run_start_time = time.time()

    async def process_chunk(t1_str, t2_str):
        """Worker function to execute a single chunk query."""
        # Fully qualify target measurement to allow cross-source_database copying.
        query_read = f'SELECT * FROM "{source_database}".."{source_measurement}" WHERE time >= \'{t1_str}\' AND time < \'{t2_str}\''

        max_retries = 5
        retry_delay = 2 # seconds

        for attempt in range(1, max_retries + 1):
            try:
                # 1. Read data
                result = await async_source_client.query(query_read)
                points = []
                if 'results' in result and result['results']:
                    for r in result['results']:
                        if 'series' in r:
                            for s in r['series']:
                                cols = s.get('columns', [])
                                vals = s.get('values', [])
                                for v in vals:
                                    points.append(dict(zip(cols, v)))

                if not points:
                    return 0

                # 2. Process data with pandas
                points_df = pd.DataFrame(points)
                if points_df.empty:
                    return 0

                new_points_batch = []

                times = points_df.pop('time')

                for index_key_tuple, uid in uid_index.items():
                    index_dict = dict(index_key_tuple)
                    req_valname = index_dict.pop('__valname__')

                    if req_valname not in points_df.columns:
                        continue

                    mask = pd.Series(True, index=points_df.index)
                    for k, v in index_dict.items():
                        if k in points_df.columns:
                            # A row matches if its value for column k exactly matches the configured value v,
                            # OR if the value in the dataframe is missing (NaN/None), acting as a wildcard
                            # to tolerate incomplete tag sets in InfluxDB points.
                            mask &= ((points_df[k] == v) | points_df[k].isna())
                        else:
                            # If the column is entirely missing from the chunk, it's effectively NaN for all rows.
                            # So it acts as a wildcard and does not fail the match.
                            pass

                    mask = mask & points_df[req_valname].notna()

                    # Process the matched rows in mask
                    if mask.any():
                        matched_df = points_df[mask]
                        matched_times = times[mask]

                        field_vals = matched_df[req_valname]

                        # Drop the field column from the dataframe used for tags
                        tags_df = matched_df.drop(columns=[req_valname])

                        # Select only string/object columns for tags
                        string_cols = tags_df.select_dtypes(include=['object', 'string']).columns
                        tags_df = tags_df[string_cols].copy()

                        # Add UID to tags
                        tags_df['UID'] = uid

                        # Create a list of tag dicts (dropping NaNs)
                        tags_records = [
                            {k: str(v) for k, v in record.items() if pd.notna(v)}
                            for record in tags_df.to_dict('records')
                        ]

                        # Assemble the batch
                        for t, tag_dict, fval in zip(matched_times, tags_records, field_vals):
                            new_points_batch.append({
                                "measurement": target_measurement,
                                "time": t,
                                "tags": tag_dict,
                                "fields": {
                                    req_valname: fval
                                }
                            })

                        # Mark processed so they aren't processed again
                        points_df.loc[mask, req_valname] = pd.NA

                # 3. Write to target
                if new_points_batch:
                    await async_target_client.write(new_points_batch)
                    return len(new_points_batch)
                return 0

            except (InfluxDBServerError, InfluxDBClientError) as e:
                logger.warning(f"Chunk {t1_str}->{t2_str} attempt {attempt} failed: {e}")
                if attempt < max_retries:                                                                       #ToDo: Write 906 in 668 instead of 906
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
            except Exception as e:
                logger.error(f"Unexpected error on chunk {t1_str}->{t2_str}: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2


        logger.error(f"Failed to process chunk {t1_str} -> {t2_str} after {max_retries} attempts.")
        raise RuntimeError(f"Chunk failure: {t1_str} -> {t2_str}")

    try:
        # We process in batches equal to max_concurrent_queries.
        # This keeps state saving robust—we only advance the state when a full batch is safely completed.
        async with async_source_client, async_target_client:
            while current_time < end_time:
                if max_chunks_per_run and chunks_processed_this_run >= max_chunks_per_run:
                    logger.info(f"Reached MAX_CHUNKS_PER_RUN limit of {max_chunks_per_run}. Pausing.")
                    break

                # Prepare a batch of chunks
                batch_tasks = []
                batch_end_time = current_time

                for _ in range(max_concurrent_queries):
                    if batch_end_time >= end_time:
                        break
                    if max_chunks_per_run and (chunks_processed_this_run + len(batch_tasks)) >= max_chunks_per_run:
                        break

                    next_time = batch_end_time + chunk_delta
                    if next_time > end_time:
                        next_time = end_time

                    t1 = batch_end_time.isoformat().replace('+00:00', 'Z')
                    t2 = next_time.isoformat().replace('+00:00', 'Z')

                    task = asyncio.create_task(process_chunk(t1, t2))
                    batch_tasks.append(task)
                    batch_end_time = next_time

                if not batch_tasks:
                    break

                # Wait for the current batch to finish
                try:
                    results = await asyncio.gather(*batch_tasks)
                    for points_in_chunk in results:
                        total_points_written += points_in_chunk
                        chunk_count += 1
                        chunks_processed_this_run += 1
                except RuntimeError as e:
                    logger.error("Aborting backup due to chunk failure. Please investigate and resume from this timestamp.")
                    sys.exit(1)

                # Batch is complete. It is now safe to advance the master current_time and save state.
                current_time = batch_end_time

                # Log progress periodically
                log_interval = max(1, int(total_chunks * 0.05)) # Log roughly every 5% instead of 0.1% to avoid spam but guarantee output
                if chunk_count == len(batch_tasks) or chunk_count == total_chunks or chunk_count % log_interval < max_concurrent_queries:
                    percentage = (chunk_count / total_chunks) * 100

                    if initial_source_count is not None and initial_source_count > 0:
                        points_remaining = max(0, initial_source_count - total_points_written)
                        logger.info(f"Progress: [{chunk_count}/{total_chunks}] chunks ({percentage:.1f}%) | "
                                    f"Copied {total_points_written:,} points | Remaining: ~{points_remaining:,}")
                    else:
                        logger.info(f"Progress: [{chunk_count}/{total_chunks}] chunks ({percentage:.1f}%) | "
                                    f"Copied {total_points_written:,} points")
                else:
                    # Debug print to ensure user knows it's doing something if they get anxious
                    print(f"Processed batch ending at {batch_end_time.isoformat()}...", end="\r", flush=True)

                # Save state after successful batch
                save_state({
                    'current_time': current_time.isoformat(),
                    'chunk_count': chunk_count,
                    'total_points_written': total_points_written,
                    'source_database': source_database,
                    'source_measurement': source_measurement,
                    'target_measurement': target_measurement
                })

    except KeyboardInterrupt:
        logger.info("\nReceived pause signal (Ctrl+C). Waiting for active queries in the current batch to finish, then exiting gracefully...")
        # The context manager automatically waits for running futures to finish before exiting the block.
        # We don't advance the state file, so the next run will correctly retry the interrupted batch.
        sys.exit(0)

    run_end_time = time.time()
    elapsed_seconds = run_end_time - run_start_time
    elapsed_timedelta = timedelta(seconds=int(elapsed_seconds))

    if current_time >= end_time:
        logger.info("Backup process finished entirely!")
        logger.info(f"Total points written across all chunks: {total_points_written:,}")
        logger.info(f"Time taken for this run: {elapsed_timedelta}")
        clear_state()

        # Final verification
        if initial_source_count is not None and initial_source_count > 0:
            logger.info("Verifying copied data...")
            final_target_count = count_measurement_points(source_client, target_database, target_measurement, start_time, end_time)

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
    else:
        logger.info(f"Backup paused at {current_time.isoformat()}. Run the script again to resume.")
        logger.info(f"Time taken for this run: {elapsed_timedelta}")

if __name__ == "__main__":
    asyncio.run(async_main())
