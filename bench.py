"""Benchmark Logging and Export for FLUX.
Reference: Section B10 & Section H.
Records user benchmark trials into CSV files with exact schema.
"""

import os
import csv
import io
import threading
from typing import Dict, Any, List, Optional
from .config import BENCH_LOGS_DIR, BENCH_COLUMNS


class BenchmarkStorage:
    """Thread-safe CSV storage for benchmark trials."""

    def __init__(self, logs_dir: str = BENCH_LOGS_DIR):
        self.logs_dir = logs_dir
        os.makedirs(self.logs_dir, exist_ok=True)
        self._rows: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def log_trial(self, row_data: Dict[str, Any]) -> bool:
        """Validate and append a benchmark trial row to memory and disk."""
        # Clean and validate fields
        session_id = str(row_data.get("session_id", "default_session"))
        
        row = {}
        for col in BENCH_COLUMNS:
            row[col] = row_data.get(col, "")

        with self._lock:
            self._rows.append(row)
            
            # Write to session CSV file
            file_path = os.path.join(self.logs_dir, f"{session_id}.csv")
            file_exists = os.path.exists(file_path)

            try:
                with open(file_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=BENCH_COLUMNS)
                    if not file_exists:
                        writer.writeheader()
                    writer.writerow(row)
                return True
            except Exception as e:
                print(f"[Bench] Error writing CSV row: {e}")
                return False

    def export_csv(self, session_id: Optional[str] = None) -> str:
        """Export stored benchmark rows as a CSV string."""
        with self._lock:
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=BENCH_COLUMNS)
            writer.writeheader()

            if session_id:
                # Read from disk if exists, else from memory
                file_path = os.path.join(self.logs_dir, f"{session_id}.csv")
                if os.path.exists(file_path):
                    with open(file_path, "r", encoding="utf-8") as f:
                        return f.read()
                filtered = [r for r in self._rows if r.get("session_id") == session_id]
                for r in filtered:
                    writer.writerow(r)
            else:
                for r in self._rows:
                    writer.writerow(r)

            return output.getvalue()


# Global benchmark storage singleton
bench_storage = BenchmarkStorage()
