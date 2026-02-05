"""CSV Converter for Shelly EM Historical Data.

Converts Shelly EM energy CSV data to statistics format.
Supports both CSV file export and direct HA native statistics import.

Shelly EM CSV format (input):
    Date/time UTC,Active energy Wh (1),Returned energy Wh (1),Min V,Max V
    2025-12-27 00:00,2.10,0.00,232.0,233.5
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


def parse_shelly_csv(csv_data: str) -> dict[str, float]:
    """Parse Shelly EM CSV data into hourly aggregated energy values.
    
    Args:
        csv_data: Raw CSV string from Shelly EM device
        
    Returns:
        Dictionary mapping hour timestamps to energy deltas (Wh)
        Example: {"2025-12-27 00:00": 12.5, "2025-12-27 01:00": 8.3}
    """
    reader = csv.reader(io.StringIO(csv_data))
    
    # Skip header
    header = next(reader, None)
    if not header:
        _LOGGER.warning("Empty CSV data")
        return {}
    
    _LOGGER.debug("CSV header: %s", header)
    
    # Aggregate 10-minute intervals to hourly
    hourly_data: dict[str, float] = {}
    
    for row in reader:
        if len(row) < 2:
            continue
        
        try:
            timestamp_str = row[0].strip()
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M")
            hour_key = timestamp.strftime("%Y-%m-%d %H:00")
            energy_delta = float(row[1].strip())
            
            hourly_data[hour_key] = hourly_data.get(hour_key, 0.0) + energy_delta
            
        except (ValueError, IndexError) as err:
            _LOGGER.debug("Skipping invalid row %s: %s", row, err)
            continue
    
    return hourly_data


def parse_shelly_csv_for_import(csv_data: str) -> list[tuple[datetime, float]]:
    """Parse Shelly EM CSV data for direct HA statistics import.
    
    Args:
        csv_data: Raw CSV string from Shelly EM device
        
    Returns:
        List of (datetime_utc, delta_wh) tuples, sorted by time
    """
    hourly_data = parse_shelly_csv(csv_data)
    
    result = []
    for hour_key in sorted(hourly_data.keys()):
        dt_utc = datetime.strptime(hour_key, "%Y-%m-%d %H:%M")
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        delta = hourly_data[hour_key]
        result.append((dt_utc, delta))
    
    return result


def convert_to_statistics_format(
    hourly_data: dict[str, float],
    statistic_id: str,
) -> list[list[str]]:
    """Convert hourly energy data to homeassistant-statistics CSV rows.
    
    Timestamps are kept in UTC - the import service will be told they are UTC
    so HA can store them correctly (HA stores all statistics in UTC internally).
    
    Args:
        hourly_data: Dictionary of hour timestamps (UTC) to energy deltas
        statistic_id: The statistic ID (e.g., sensor.shellyem_xxx_energy)
        
    Returns:
        List of CSV rows including header
    """
    rows = [["statistic_id", "start", "delta", "unit"]]
    
    for hour_key in sorted(hourly_data.keys()):
        delta = hourly_data[hour_key]
        # Parse UTC timestamp and format for output (keep as UTC)
        dt_utc = datetime.strptime(hour_key, "%Y-%m-%d %H:%M")
        formatted_time = dt_utc.strftime("%d.%m.%Y %H:%M")
        rows.append([statistic_id, formatted_time, f"{delta:.2f}", "Wh"])
    
    return rows


def rows_to_csv_string(rows: list[list[str]]) -> str:
    """Convert rows to CSV string.
    
    Args:
        rows: List of CSV rows including header
        
    Returns:
        CSV formatted string
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=",")
    writer.writerows(rows)
    return output.getvalue()


def _write_file_sync(output_path: Path, content: str) -> None:
    """Write content to file synchronously (for executor)."""
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        f.write(content)


def build_statistic_id(hostname: str, channel: int) -> str:
    """Build a statistic ID matching the existing HA entity.
    
    Maps to existing HA entities created by shelly_integrator:
    - Channel 0 → sensor.shellyem_<mac>_energy
    - Channel 1 → sensor.shellyem_<mac>_energy_2
    
    Uses '.' separator (internal statistic) to match existing entity,
    which allows delta import to work immediately.
    
    Args:
        hostname: Device hostname (e.g., shellyem-48E729689B2B)
        channel: Channel number (0-indexed)
        
    Returns:
        Statistic ID matching existing HA entity
        (e.g., sensor.shellyem_48e729689b2b_energy)
    """
    safe_hostname = hostname.lower().replace("-", "_")
    if channel == 0:
        return f"sensor.{safe_hostname}_energy"
    else:
        return f"sensor.{safe_hostname}_energy_{channel + 1}"


def build_output_filename(hostname: str, channel: int) -> str:
    """Build output filename for converted CSV.
    
    Matches entity naming pattern:
    - Channel 0 → shelly_import_shellyem_xxx_energy.csv
    - Channel 1 → shelly_import_shellyem_xxx_energy_2.csv
    
    Args:
        hostname: Device hostname
        channel: Channel number (0-indexed)
        
    Returns:
        Filename matching entity naming pattern
    """
    safe_hostname = hostname.lower().replace("-", "_")
    if channel == 0:
        return f"shelly_import_{safe_hostname}_energy.csv"
    else:
        return f"shelly_import_{safe_hostname}_energy_{channel + 1}.csv"


async def convert_channel_csv(
    hass: "HomeAssistant",
    csv_data: str,
    hostname: str,
    channel: int,
    config_path: str,
) -> str | None:
    """Convert a single channel's CSV data and save to file.
    
    This is the main conversion function that orchestrates:
    1. Parsing the raw Shelly CSV
    2. Converting to statistics format
    3. Saving to file (async via executor)
    
    Args:
        hass: Home Assistant instance
        csv_data: Raw CSV string from Shelly EM device
        hostname: Device hostname
        channel: Channel number (0-indexed)
        config_path: Home Assistant config directory path
        
    Returns:
        Output file path if successful, None otherwise
    """
    try:
        hourly_data = parse_shelly_csv(csv_data)
        
        if not hourly_data:
            _LOGGER.warning("No valid data found for %s channel %d", hostname, channel)
            return None
        
        statistic_id = build_statistic_id(hostname, channel)
        # Keep timestamps in UTC - import service will be told they are UTC
        rows = convert_to_statistics_format(hourly_data, statistic_id)
        
        output_filename = build_output_filename(hostname, channel)
        output_path = Path(config_path) / output_filename
        
        # Convert rows to CSV string
        csv_content = rows_to_csv_string(rows)
        
        # Write file using executor to avoid blocking
        await hass.async_add_executor_job(_write_file_sync, output_path, csv_content)
        
        _LOGGER.info("Saved %d rows to %s", len(rows) - 1, output_path)
        _LOGGER.info(
            "Converted %d hours of data for %s channel %d",
            len(hourly_data), hostname, channel
        )
        
        return str(output_path)
        
    except Exception as err:
        _LOGGER.exception("Error converting CSV for %s channel %d: %s", hostname, channel, err)
        return None
