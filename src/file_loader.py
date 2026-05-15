import pandas as pd
import csv
import re


def get_tags_from_taglist(taglist_filename) -> dict:
    try:
        with open(taglist_filename, 'r', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)

            config_name_map = {}

            for row in reader:
                if not row or not row[0].strip() or row[0].strip().startswith('#'):
                    continue

                if len(row) < 12:       # skip empty lines and comments (lines starting with #)
                    continue

                row_cleaned = [col.strip() for col in row]      # rows without leading/trailing whitespace

                config_name = row_cleaned[-1].strip()

                tag_details =  {
                    "UID": re.sub(r'[{}]', '', row_cleaned[0]),
                    "measurement": row_cleaned[1],
                    "measurand": row_cleaned[2],
                    "valname": row_cleaned[3],
                    "basekv": row_cleaned[4],
                    "device": row_cleaned[5],
                    "bldng": row_cleaned[6],
                    "bay": row_cleaned[7],
                    "dest": row_cleaned[8],
                    "phase": row_cleaned[9],
                    "unit": row_cleaned[10]
                }

                tags = {k: v for k, v in tag_details.items() if v and v != '-'}  # Filter out empty and '-' values

                config_name_map[config_name] = tags

        return config_name_map
    except Exception as e:
        print(f"Fehler beim Einlesen: {e}")
        return {}


def get_uid_for_tagset(taglist_file):
    tags_dict = get_tags_from_taglist(taglist_file)
    uid_index = {}
    for tag_key, tag_data in tags_dict.items():
        if 'UID' not in tag_data:
            logger.warning(f"Skipping tag config '{tag_key}' because it is missing a UID.")
            continue

        uid = tag_data['UID']
        valname = tag_data.get('valname', '')

        match_criteria = {}
        for k, v in tag_data.items():
            if k not in ('UID', 'measurement', 'valname'):
                match_criteria[k] = v

        # Create hashable tuple as key
        key_tuple = tuple(sorted(match_criteria.items())) + (('__valname__', valname),)
        uid_index[key_tuple] = uid
    return uid_index
