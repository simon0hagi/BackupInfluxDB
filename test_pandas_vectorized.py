import pandas as pd
import numpy as np

# Simulate a small data chunk
data = [
    {"time": "2023-01-01T00:00:00Z", "measurement": "A", "valname": "temp", "device": "d1", "temp": 25.5},
    {"time": "2023-01-01T00:01:00Z", "measurement": "A", "valname": "temp", "device": "d2", "temp": 26.5},
    {"time": "2023-01-01T00:02:00Z", "measurement": "B", "valname": "press", "device": "d1", "press": 101.3},
    {"time": "2023-01-01T00:03:00Z", "measurement": "A", "valname": "temp", "device": "d1", "temp": None},
]

df = pd.DataFrame(data)

uid_index = {
    (('device', 'd1'), ('measurement', 'A'), ('__valname__', 'temp')): 'uid1',
    (('device', 'd2'), ('measurement', 'A'), ('__valname__', 'temp')): 'uid2',
    (('device', 'd1'), ('measurement', 'B'), ('__valname__', 'press')): 'uid3',
}

target_measurement = "Backup"
new_points_batch = []
times = df.pop('time')

for index_key_tuple, uid in uid_index.items():
    index_dict = dict(index_key_tuple)
    req_valname = index_dict.pop('__valname__')

    if req_valname not in df.columns:
        continue

    # Build the mask vectorized
    mask = pd.Series(True, index=df.index)
    for k, v in index_dict.items():
        if k in df.columns:
            mask &= ((df[k] == v) | df[k].isna())

    mask &= df[req_valname].notna()

    if mask.any():
        matched_df = df[mask].copy()
        matched_times = times[mask]

        # Vectorized way to construct list of dicts.
        # We need "tags" and "fields" dictionaries for each matched row.

        # Get field values
        field_vals = matched_df[req_valname]

        # Drop the field column from the dataframe used for tags
        tags_df = matched_df.drop(columns=[req_valname])

        # Select only string/object columns for tags
        string_cols = tags_df.select_dtypes(include=['object', 'string']).columns
        tags_df = tags_df[string_cols]

        # Add UID to tags
        tags_df['UID'] = uid

        # Create a list of tag dicts (dropping NaNs)
        # Using a list comprehension over zip is usually much faster than iterrows
        # But we also have to drop NaNs from each dict.

        # The fastest way is to pre-compute the non-nulls by constructing dicts:
        tags_records = [
            {k: str(v) for k, v in record.items() if pd.notna(v)}
            for record in tags_df.to_dict('records')
        ]

        # Now assemble the batch
        for t, tag_dict, fval in zip(matched_times, tags_records, field_vals):
            new_points_batch.append({
                "measurement": target_measurement,
                "time": t,
                "tags": tag_dict,
                "fields": {req_valname: fval}
            })

        # Mark processed
        df.loc[mask, req_valname] = pd.NA

print(new_points_batch)
