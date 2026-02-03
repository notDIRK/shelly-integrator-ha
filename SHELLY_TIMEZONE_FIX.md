# Shelly Integrator - Timezone Fix

## Problem

ApexCharts shows dates shifted by 1 day when using statistics-based aggregation.

## Root Cause

1. Shelly EM CSV data is in **UTC** (`Date/time UTC` column)
2. HA stores statistics in **UTC** internally
3. ApexCharts aggregates by UTC day boundaries, not local day boundaries
4. `homeassistant-statistics` import doesn't know the timezone of the input

## Solution (Recommended)

### 1. Keep timestamps in UTC throughout

```python
from datetime import datetime

# Parse UTC timestamp from Shelly CSV
utc_time = datetime.strptime(row['Date/time UTC'], '%Y-%m-%d %H:%M')

# Output in UTC - do NOT convert to local time
output_timestamp = utc_time.strftime('%d.%m.%Y %H:%M')
```

### 2. Specify UTC timezone on import

```python
await hass.services.async_call(
    "import_statistics",
    "import_from_file",
    {
        "filename": output_filename,
        "delimiter": ",",
        "decimal": ".",
        "datetime_format": "%d.%m.%Y %H:%M",
        "timezone_identifier": "UTC",  # CRITICAL - tell import the timestamps are UTC
        "unit_from_entity": True,
    },
)
```

### 3. Use HA's timezone utilities (for any local time needs)

```python
from homeassistant.util import dt as dt_util

# Get HA's configured timezone dynamically (don't hardcode!)
local_tz = dt_util.DEFAULT_TIME_ZONE

# Convert UTC to local if needed for display
local_time = utc_time.replace(tzinfo=dt_util.UTC).astimezone(local_tz)

# Convert local to UTC for storage
utc_time = local_time.astimezone(dt_util.UTC)
```

## Why This Works

- HA stores all statistics in UTC
- By importing with `timezone_identifier: "UTC"`, HA knows the timestamps are already UTC
- HA's recorder and frontend handle timezone conversion for display
- Works for users in ANY timezone

## Files to Update in shelly-integrator-ha

1. **`csv_converter.py`** (or equivalent):
   - Keep Shelly CSV timestamps as UTC
   - Don't convert to local time

2. **`__init__.py`** (service call):
   - Add `"timezone_identifier": "UTC"` to import_statistics call

## Dashboard Note

For accurate daily aggregation by local timezone, users should use:
- HA's native **Energy Dashboard** (handles timezone correctly)
- **`utility_meter`** sensors (aggregates by local day)

ApexCharts statistics mode aggregates by UTC day, which may not match local day boundaries.
