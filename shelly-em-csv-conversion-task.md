# Shelly EM CSV Conversion Task

## Problem

The Shelly EM device stores historical energy data in **10-minute intervals**, but Home Assistant's long-term statistics requires **hourly** data. The `shelly-integrator-ha` HACS component needs to convert the raw CSV into a format compatible with the `homeassistant-statistics` integration.

---

## Source Data Format

**File**: Shelly EM exports CSV from `http://<device-ip>/emeter/0/em_data.csv`

**Columns**:
```csv
Date/time UTC,Active energy Wh (1),Returned energy Wh (1),Min V,Max V
2025-12-27 00:00,2.10,0.00,232.0,233.5
2025-12-27 00:10,2.10,0.00,232.0,233.5
2025-12-27 00:20,2.10,0.00,232.0,233.5
...
```

| Column | Description |
|--------|-------------|
| `Date/time UTC` | Timestamp in UTC, 10-minute intervals |
| `Active energy Wh (1)` | Energy consumed in that 10-min period (Wh) |
| `Returned energy Wh (1)` | Energy returned/exported (Wh) |
| `Min V` | Minimum voltage during period |
| `Max V` | Maximum voltage during period |

**Data Characteristics**:
- 10-minute granularity (6 records per hour)
- Values are **delta** (energy for that period, not cumulative)
- Timestamps are in UTC
- ~14,700 rows for 5 weeks of data

---

## Target Data Format

**For**: `homeassistant-statistics` integration (HACS)

**Required Format** (delta import):
```csv
statistic_id,start,delta,unit
sensor:shellyem_48e729689b2b_ch1_energy,27.12.2025 00:00,12.40,Wh
sensor:shellyem_48e729689b2b_ch1_energy,27.12.2025 01:00,13.00,Wh
sensor:shellyem_48e729689b2b_ch1_energy,27.12.2025 02:00,12.60,Wh
```

| Column | Description |
|--------|-------------|
| `statistic_id` | Format: `sensor:<device_mac>_ch<N>_energy` (external statistic with `:`) |
| `start` | Timestamp in local timezone, format: `DD.MM.YYYY HH:MM` |
| `delta` | Sum of all 10-min values for that hour |
| `unit` | Always `Wh` for energy |

**Requirements**:
- Must be **hourly** data (minutes must be `:00`)
- Timestamps in **local timezone** (Europe/Istanbul for this deployment)
- Use **delta** column (not sum/state) - this is the recommended approach
- `statistic_id` uses `:` separator (external statistic) not `.` (internal entity)

---

## Conversion Logic

### 1. Group by Hour
```python
# Group 10-minute records into hourly buckets
# 00:00, 00:10, 00:20, 00:30, 00:40, 00:50 → 00:00
# 01:00, 01:10, 01:20, 01:30, 01:40, 01:50 → 01:00
```

### 2. Sum Energy Values
```python
# For each hour, sum the "Active energy Wh" values
hourly_delta = sum(10_min_values_in_hour)
# Example: 2.10 + 2.10 + 2.10 + 2.00 + 2.10 + 2.00 = 12.40 Wh
```

### 3. Convert Timezone
```python
# Input is UTC, output should be local timezone
from datetime import datetime, timezone
import pytz

utc_time = datetime.strptime(row['Date/time UTC'], '%Y-%m-%d %H:%M')
utc_time = utc_time.replace(tzinfo=timezone.utc)
local_tz = pytz.timezone('Europe/Istanbul')  # or from HA config
local_time = utc_time.astimezone(local_tz)
output_timestamp = local_time.strftime('%d.%m.%Y %H:%M')
```

### 4. Generate Output
```python
# Output format for homeassistant-statistics
output_row = {
    'statistic_id': f'sensor:shellyem_{device_mac}_ch{channel}_energy',
    'start': output_timestamp,  # DD.MM.YYYY HH:MM
    'delta': round(hourly_delta, 2),
    'unit': 'Wh'
}
```

---

## Implementation in shelly-integrator-ha

### Service: `shelly_integrator.convert_historical_data`

**Flow**:
1. Fetch CSV from gateway proxy: `https://silver.oldtownsultanahmet.com/sensor/emeter/0/em_data.csv`
2. Parse CSV with pandas or csv module
3. Convert UTC to local timezone
4. Group by hour and sum energy values
5. Write to `/config/shelly_import_<device>_ch<N>.csv`

### Code Location

Add conversion logic to `shelly-integrator-ha/custom_components/shelly_integrator/`:

```
shelly_integrator/
├── __init__.py
├── services.py          # Add convert_historical_data service
├── csv_converter.py     # NEW: Conversion logic
└── ...
```

### Service Definition (services.yaml)

```yaml
convert_historical_data:
  name: Convert Historical Data
  description: Fetch and convert Shelly EM historical CSV to HA statistics format
  fields:
    device_id:
      name: Device ID
      description: Shelly device ID or MAC address
      example: "shellyem_48e729689b2b"
      required: false
    gateway_url:
      name: Gateway URL
      description: URL to fetch CSV from
      example: "https://silver.oldtownsultanahmet.com/sensor"
      required: false
```

---

## Example Conversion

### Input (em_data.csv - 10min intervals)
```csv
Date/time UTC,Active energy Wh (1),Returned energy Wh (1),Min V,Max V
2025-12-27 00:00,2.10,0.00,232.0,233.5
2025-12-27 00:10,2.10,0.00,232.0,233.5
2025-12-27 00:20,2.10,0.00,232.0,233.5
2025-12-27 00:30,2.00,0.00,232.0,233.5
2025-12-27 00:40,2.10,0.00,232.0,233.5
2025-12-27 00:50,2.00,0.00,232.0,233.5
2025-12-27 01:00,2.00,0.00,232.0,233.5
2025-12-27 01:10,2.10,0.00,233.5,235.0
...
```

### Output (shelly_import_shellyem_48e729689b2b_ch1.csv)
```csv
statistic_id,start,delta,unit
sensor:shellyem_48e729689b2b_ch1_energy,27.12.2025 03:00,12.40,Wh
sensor:shellyem_48e729689b2b_ch1_energy,27.12.2025 04:00,12.20,Wh
...
```

*Note: 00:00 UTC = 03:00 Europe/Istanbul*

---

## Testing

1. Place `em_data.csv` in HA config directory
2. Call `shelly_integrator.convert_historical_data`
3. Check output file exists in `/config/`
4. Import with `import_statistics.import_from_file`
5. Verify in Developer Tools → Statistics

---

## Related Files

- **Source CSV**: `http://<device-ip>/emeter/0/em_data.csv` (or via gateway)
- **Output CSV**: `/config/shelly_import_shellyem_48e729689b2b_ch1.csv`
- **Import Service**: `import_statistics.import_from_file`

## Dependencies

- `homeassistant-statistics` HACS integration (for import)
- `pytz` for timezone conversion (usually available in HA)
