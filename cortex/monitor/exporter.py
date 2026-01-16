"""
Data export functionality for monitoring system.
Handles JSON and CSV export formats.
This module provides data export capabilities for system monitoring data,
supporting both JSON (for structured analysis) and CSV (for spreadsheet
import) formats. It handles data serialization, file operations, and
error handling with specific exceptions.
"""

import csv
import json
import logging
import os
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from cortex.history import InstallationHistory, InstallationType
from cortex.monitor.resource_monitor import ResourceMonitor

# Set up logging
logger = logging.getLogger(__name__)


# export to json main api
def export_to_json(
    history: list[dict[str, Any]],
    peak_usage: dict[str, float],
    output_file: str,
    include_recommendations: bool = False,
    get_recommendations_func: Callable[[], list[str]] | None = None,
) -> None:
    if not output_file or not output_file.strip():
        raise ValueError(f"Invalid output_file: {output_file!r}")
    """
    Convenience function to export monitoring data from a ResourceMonitor instance.

    Args:
        monitor: ResourceMonitor instance with get_history() and get_peak_usage() methods
        format_type: 'json' or 'csv' (case-insensitive)
        output_file: Path to output file (must be non-empty string)
        include_recommendations: Whether to include recommendations (JSON only)

    Raises:
        ValueError: If output_file is invalid or data cannot be serialized.
        TypeError: If history or peak_usage have invalid types.
        OSError: If the file system operation fails.
    """
    _validate_export_inputs(output_file, history, peak_usage)

    try:
        _ensure_output_dir(output_file)

        payload = _build_payload(history, peak_usage)

        _add_recommendations(
            payload,
            include_recommendations,
            get_recommendations_func,
        )

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)

        logger.info("JSON export successful: %s", output_file)
        _audit_export(
            format_type="json",
            output_file=output_file,
            result="success",
        )

    except OSError as exc:
        logger.error(
            "File system error during JSON export to %s: %s",
            output_file,
            exc,
        )
        _audit_export(
            format_type="json",
            output_file=output_file,
            result="failure",
            error=str(exc),
        )
        raise

    except (json.JSONDecodeError, TypeError) as exc:
        logger.error("Data serialization error during JSON export: %s", exc)
        _audit_export(
            format_type="json",
            output_file=output_file,
            result="failure",
            error=str(exc),
        )
        raise ValueError(f"Data cannot be serialized to JSON: {exc}") from exc


# helper function
def _validate_export_inputs(
    output_file: str,
    history: list,
    peak_usage: dict,
) -> None:
    """
    Validate inputs provided to the export functions.

    Args:
        output_file: Path to the output file.
        history: Monitoring history data.
        peak_usage: Peak usage statistics.

    Raises:
        ValueError: If output_file is empty or not a string.
        TypeError: If history is not a list or peak_usage is not a dict.
    """
    if not output_file or not isinstance(output_file, str):
        raise ValueError(f"Invalid output_file: {output_file!r}")

    if not isinstance(history, list):
        raise TypeError(f"history must be a list, got {type(history).__name__}")

    if not isinstance(peak_usage, dict):
        raise TypeError(f"peak_usage must be a dict, got {type(peak_usage).__name__}")


def _ensure_output_dir(output_file: str) -> None:
    """
    Ensure the output directory for the given file path exists.

    Creates the directory structure if it does not already exist.
    If the output file is in the current directory, no action is taken.

    Args:
        output_file: Path to the output file.
    """
    output_dir = os.path.dirname(os.path.abspath(output_file))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)


def _build_payload(
    history: list[dict[str, Any]],
    peak_usage: dict[str, float],
) -> dict[str, Any]:
    """
    Build the base JSON payload for export.

    The payload includes metadata, peak resource usage, and
    the collected monitoring samples.

    Args:
        history: List of monitoring samples.
        peak_usage: Peak resource usage metrics.

    Returns:
        A dictionary representing the JSON export payload.
    """
    return {
        "metadata": {
            "export_timestamp": time.time(),
            "export_date": time.ctime(),
            "samples_count": len(history),
            "format_version": "1.0",
        },
        "peak_usage": peak_usage,
        "samples": history,
    }


def _add_recommendations(
    payload: dict[str, Any],
    include: bool,
    func: Callable[[], list[str]] | None,
) -> None:
    """
    Add performance recommendations to the export payload if enabled.

    This function must NEVER raise, even on unexpected errors.
    """
    if not include or not func:
        return

    try:
        recommendations = func()

        if isinstance(recommendations, list):
            payload["recommendations"] = recommendations
            logger.debug("Added recommendations to JSON export")
        else:
            logger.warning(
                "get_recommendations_func returned non-list: %s",
                type(recommendations).__name__,
            )

    except (AttributeError, TypeError, ValueError) as exc:
        # Expected, recoverable errors
        logger.warning("Error generating recommendations: %s", exc)

    except Exception as exc:
        logger.warning("Unexpected error generating recommendations: %s", exc)


# export to csv main api
def export_to_csv(
    history: list[dict[str, Any]],
    output_file: str,
) -> None:
    if not output_file or not output_file.strip():
        raise ValueError(f"Invalid output_file: {output_file!r}")
    """
    Export monitoring history to a CSV file.

    This function performs the complete CSV export workflow:
    - Validates input arguments
    - Ensures the output directory exists
    - Handles empty history gracefully
    - Dynamically determines CSV headers
    - Writes normalized rows to the CSV file

    Args:
        history: List of monitoring samples collected over time.
        output_file: File path where the CSV export will be written.

    Raises:
        ValueError: If output_file is invalid or history has inconsistent structure.
        TypeError: If history is not a list.
        OSError: If the file system operation fails.
    """
    _validate_csv_inputs(output_file, history)

    try:
        _ensure_output_dir(output_file)

        if not history:
            _write_empty_csv(output_file)
            logger.info("Empty CSV export created: %s", output_file)
            _audit_export(
                format_type="csv",
                output_file=output_file,
                result="success",
            )
            return

        fieldnames = _extract_csv_fieldnames(history)

        _write_csv_rows(history, fieldnames, output_file)

        logger.info("CSV export successful: %s (%d rows)", output_file, len(history))
        _audit_export(
            format_type="csv",
            output_file=output_file,
            result="success",
        )

    except OSError as exc:
        logger.error(
            "File system error during CSV export to %s: %s",
            output_file,
            exc,
        )
        raise

    except csv.Error as exc:
        logger.error("CSV formatting error: %s", exc)
        _audit_export(
            format_type="csv",
            output_file=output_file,
            result="failure",
            error=str(exc),
        )
        raise ValueError(f"CSV formatting error: {exc}") from exc


# helper func for valid csv input
def _validate_csv_inputs(output_file: str, history: list) -> None:
    """
    Validate inputs provided to the CSV export function.

    Args:
        output_file: Path to the output CSV file.
        history: Monitoring history data.

    Raises:
        ValueError: If output_file is empty or not a string.
        TypeError: If history is not a list.
    """
    if not output_file or not isinstance(output_file, str):
        raise ValueError(f"Invalid output_file: {output_file!r}")

    if not isinstance(history, list):
        raise TypeError(f"history must be a list, got {type(history).__name__}")


# helper function for write empty csv
def _write_empty_csv(output_file: str) -> None:
    """
    Write a CSV file containing only standard headers when no data is available.

    Args:
        output_file: Path to the output CSV file.
    """
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "cpu_percent",
                "memory_percent",
                "disk_percent",
                "alerts",
            ],
        )
        writer.writeheader()


# helper func for check extra csv field names
def _extract_csv_fieldnames(history: list[dict[str, Any]]) -> list[str]:
    """
    Extract and normalize CSV fieldnames from monitoring history.

    Args:
        history: List of monitoring samples.

    Returns:
        A sorted list of unique field names.

    Raises:
        ValueError: If samples are not dictionaries or contain no fields.
    """
    fieldnames_set: set[str] = set()

    for sample in history:
        if not isinstance(sample, dict):
            raise ValueError(f"Sample must be a dict, got {type(sample).__name__}")
        fieldnames_set.update(sample.keys())

    if not fieldnames_set:
        raise ValueError("No fieldnames found in history data")

    return sorted(fieldnames_set)


# helper for write csv rows
def _write_csv_rows(
    history: list[dict[str, Any]],
    fieldnames: list[str],
    output_file: str,
) -> None:
    """
    Write monitoring history rows to a CSV file.

    Handles normalization of values:
    - Lists are converted to semicolon-separated strings
    - None values become empty strings
    - All values are converted to strings

    Args:
        history: List of monitoring samples.
        fieldnames: CSV column headers.
        output_file: Path to the output CSV file.
    """
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for index, sample in enumerate(history):
            try:
                row: dict[str, str] = {}

                for key in fieldnames:
                    value = sample.get(key)
                    if isinstance(value, list):
                        row[key] = "; ".join(str(item) for item in value)
                    elif value is not None:
                        row[key] = str(value)
                    else:
                        row[key] = ""

                writer.writerow(row)

            except (KeyError, AttributeError) as exc:
                logger.warning(
                    "Error processing sample %d: %s",
                    index,
                    exc,
                )


def export_monitoring_data(
    monitor,
    format_type: str,
    output_file: str,
    *,
    include_recommendations: bool = True,
) -> bool:
    try:
        format_type_lower = format_type.lower()

        if not hasattr(monitor, "get_history"):
            raise AttributeError("monitor missing get_history() method")
        if not hasattr(monitor, "get_peak_usage"):
            raise AttributeError("monitor missing get_peak_usage() method")

        history = monitor.get_history()
        peak_usage = monitor.get_peak_usage()

        if format_type_lower == "json":
            get_recommendations_func = None
            if include_recommendations and hasattr(monitor, "get_recommendations"):
                get_recommendations_func = monitor.get_recommendations

            export_to_json(
                history,
                peak_usage,
                output_file,
                include_recommendations=include_recommendations,
                get_recommendations_func=get_recommendations_func,
            )

        elif format_type_lower == "csv":
            export_to_csv(history, output_file)

        else:
            raise ValueError(f"Unsupported export format: {format_type}")

        return True

    except Exception as exc:
        logger.error("Export failed for %s: %s", output_file, exc)
        return False


def export_json(
    history: list[dict[str, Any]],
    peak_usage: dict[str, float],
    output_file: str,
    **kwargs: Any,
) -> bool:
    """
    Simplified JSON export function that returns success/failure.
    Args:
        history: List of monitoring samples
        peak_usage: Peak resource usage dictionary
        output_file: Path to output JSON file
        **kwargs: Additional arguments passed to export_to_json
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        export_to_json(history, peak_usage, output_file, **kwargs)
        return True
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        logger.error("Export failed for %s: %s", output_file, exc)
        return False


def export_csv(
    history: list[dict[str, Any]],
    output_file: str,
) -> bool:
    """
    Simplified CSV export function that returns success/failure.
    Args:
        history: List of monitoring samples
        output_file: Path to output CSV file
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        export_to_csv(history, output_file)
        return True
    except (OSError, ValueError, TypeError) as exc:
        logger.error("Simplified CSV export failed: %s", exc)
        return False


def _audit_export(
    format_type: str,
    output_file: str,
    result: str,
    error: str | None = None,
) -> None:
    """
    Record an audit entry for monitoring data export operations.

    Args:
        format_type: Export format ("json" or "csv")
        output_file: Path to the exported file
        result: "success" or "failure"
        error: Optional error message if export failed
    """
    history = InstallationHistory()

    details = [
        f"format={format_type}",
        f"path={output_file}",
        f"result={result}",
    ]

    if error:
        details.append(f"error={error}")

    history.record_installation(
        InstallationType.INSTALL,
        ["monitor"],
        details,
        datetime.now(timezone.utc),
    )
