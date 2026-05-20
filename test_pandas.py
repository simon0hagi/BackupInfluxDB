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

        # We need tags to contain non-null string values, plus UID
        # Drop the value column for tags processing
        tag_cols = [c for c in matched_df.columns if c != req_valname]

        # This part in the original code:
        # non_null_row = row.dropna().to_dict()
        # field_val = non_null_row.pop(req_valname)
        # tags = {k: str(v) for k, v in non_null_row.items() if isinstance(v, str)}
        # tags['UID'] = uid

        # Let's vectorize it.
        field_vals = matched_df[req_valname]

        # Keep only string-type tags? The original says: if isinstance(v, str)
        # We can just iterate over records for the tags, but much faster:
        # Actually it's probably faster to just build the list of dicts directly from the dataframe.

        # Convert matched part to dicts using to_dict('records')
        # We need to keep only non-na, and keep string

        for idx in matched_df.index:
            row_dict = matched_df.loc[idx].dropna().to_dict()
            val = row_dict.pop(req_valname)
            tags = {k: str(v) for k, v in row_dict.items() if isinstance(v, str)}
            tags['UID'] = uid
            new_point = {
                "measurement": target_measurement,
                "time": times[idx],
                "tags": tags,
                "fields": {req_valname: val}
            }
            new_points_batch.append(new_point)

        # mark processed so they aren't processed again
        df.loc[mask, req_valname] = pd.NA

print(new_points_batch)
