"""
SQLite-based storage for DICOM Modality Worklist items.

This module provides a simple, file-based storage layer for worklist items
that can be queried by the MWL server and updated by the relay listener.

Schema is initialized separately via init_db.sql during container startup.
"""

import sqlite3
import threading
from typing import List, Dict, Optional
from contextlib import contextmanager


class WorklistStorage:
    """
    Thread-safe SQLite storage for DICOM worklist items.

    Supports concurrent reads (DICOM queries) and writes (relay listener updates).
    Uses Write-Ahead Logging (WAL) mode for better concurrency.

    The database schema must be initialized separately (see scripts/init_db.sql).
    """

    def __init__(self, db_path: str = "/var/lib/orthanc/worklist/worklist.db"):
        """
        Initialize the worklist storage.

        Args:
            db_path: Path to the SQLite database file (must already exist and be initialized)
        """
        self.db_path = db_path
        self._local = threading.local()
        self._configure_connection()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a thread-local database connection."""
        if not hasattr(self._local, 'connection'):
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.connection = conn
        return self._local.connection

    def _configure_connection(self):
        """Initialize the connection with WAL mode."""
        # Create initial connection to set up WAL mode
        conn = self._get_connection()
        conn.close()
        if hasattr(self._local, 'connection'):
            del self._local.connection

    @contextmanager
    def _transaction(self):
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def add_worklist_item(
        self,
        accession_number: str,
        patient_id: str,
        patient_name: str,
        patient_birth_date: str,
        scheduled_date: str,
        scheduled_time: str,
        modality: str,
        study_description: str = "",
        patient_sex: str = "",
        procedure_code: str = "",
        study_instance_uid: str = "",
        source_message_id: str = ""
    ) -> str:
        """
        Add a new worklist item.

        Args:
            accession_number: Unique accession number (primary key)
            patient_id: Patient identifier
            patient_name: Patient name in DICOM format (e.g., "SMITH^JANE")
            patient_birth_date: Birth date in YYYYMMDD format
            scheduled_date: Scheduled date in YYYYMMDD format
            scheduled_time: Scheduled time in HHMMSS format
            modality: Modality code (e.g., "MG" for mammography)
            study_description: Description of the study
            patient_sex: Patient sex (M/F/O)
            procedure_code: Procedure code
            study_instance_uid: DICOM Study Instance UID
            source_message_id: ID of the relay message that created this item

        Returns:
            The accession number of the created item

        Raises:
            sqlite3.IntegrityError: If accession number already exists
        """
        with self._transaction() as conn:
            conn.execute("""
                INSERT INTO worklist_items (
                    accession_number, patient_id, patient_name, patient_birth_date,
                    patient_sex, scheduled_date, scheduled_time, modality,
                    study_description, procedure_code, study_instance_uid,
                    source_message_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                accession_number, patient_id, patient_name, patient_birth_date,
                patient_sex, scheduled_date, scheduled_time, modality,
                study_description, procedure_code, study_instance_uid,
                source_message_id
            ))

        return accession_number

    def find_worklist_items(
        self,
        modality: Optional[str] = None,
        scheduled_date: Optional[str] = None,
        patient_id: Optional[str] = None,
        status: str = "SCHEDULED"
    ) -> List[Dict]:
        """
        Query worklist items with optional filters.

        Args:
            modality: Filter by modality (e.g., "MG")
            scheduled_date: Filter by scheduled date (YYYYMMDD)
            patient_id: Filter by patient ID
            status: Filter by status (default: "SCHEDULED")

        Returns:
            List of worklist items as dictionaries
        """
        query = "SELECT * FROM worklist_items WHERE status = ?"
        params = [status]

        if modality:
            query += " AND modality = ?"
            params.append(modality)

        if scheduled_date:
            query += " AND scheduled_date = ?"
            params.append(scheduled_date)

        if patient_id:
            query += " AND patient_id = ?"
            params.append(patient_id)

        query += " ORDER BY scheduled_date, scheduled_time"

        conn = self._get_connection()
        cursor = conn.execute(query, params)

        return [dict(row) for row in cursor.fetchall()]

    def get_worklist_item(self, accession_number: str) -> Optional[Dict]:
        """
        Get a single worklist item by accession number.

        Args:
            accession_number: The accession number to look up

        Returns:
            Worklist item as dictionary, or None if not found
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM worklist_items WHERE accession_number = ?",
            (accession_number,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def update_status(
        self,
        accession_number: str,
        status: str,
        mpps_instance_uid: Optional[str] = None
    ) -> Optional[str]:
        """
        Update the status of a worklist item.

        Args:
            accession_number: The accession number to update
            status: New status (SCHEDULED, IN_PROGRESS, COMPLETED, DISCONTINUED)
            mpps_instance_uid: Optional MPPS instance UID

        Returns:
            source_message_id if item was updated, None if not found
        """
        with self._transaction() as conn:
            cursor = conn.execute("""
                UPDATE worklist_items
                SET status = ?,
                    mpps_instance_uid = COALESCE(?, mpps_instance_uid),
                    updated_at = CURRENT_TIMESTAMP
                WHERE accession_number = ?
            """, (status, mpps_instance_uid, accession_number))

            if cursor.rowcount > 0:
                # Fetch the source_message_id for the updated item
                result = conn.execute(
                    "SELECT source_message_id FROM worklist_items WHERE accession_number = ?",
                    (accession_number,)
                ).fetchone()
                return result['source_message_id'] if result else None

            return None

    def update_study_instance_uid(
        self,
        accession_number: str,
        study_instance_uid: str
    ) -> bool:
        """
        Update the study instance UID for a worklist item.

        Args:
            accession_number: The accession number to update
            study_instance_uid: The Study Instance UID

        Returns:
            True if item was updated, False if not found
        """
        with self._transaction() as conn:
            cursor = conn.execute("""
                UPDATE worklist_items
                SET study_instance_uid = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE accession_number = ?
            """, (study_instance_uid, accession_number))

            return cursor.rowcount > 0

    def delete_worklist_item(self, accession_number: str) -> bool:
        """
        Delete a worklist item.

        Args:
            accession_number: The accession number to delete

        Returns:
            True if item was deleted, False if not found
        """
        with self._transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM worklist_items WHERE accession_number = ?",
                (accession_number,)
            )
            return cursor.rowcount > 0

    def get_statistics(self) -> Dict:
        """
        Get statistics about worklist items.

        Returns:
            Dictionary with counts by status
        """
        conn = self._get_connection()
        cursor = conn.execute("""
            SELECT status, COUNT(*) as count
            FROM worklist_items
            GROUP BY status
        """)

        stats = {row['status']: row['count'] for row in cursor.fetchall()}

        # Add total count
        stats['TOTAL'] = sum(stats.values())

        return stats

    def cleanup_old_items(self, days_old: int = 30) -> int:
        """
        Delete completed/discontinued worklist items older than specified days.

        Args:
            days_old: Number of days to keep items

        Returns:
            Number of items deleted
        """
        with self._transaction() as conn:
            cursor = conn.execute("""
                DELETE FROM worklist_items
                WHERE datetime(created_at) < datetime('now', '-' || ? || ' days')
                AND status IN ('COMPLETED', 'DISCONTINUED')
            """, (days_old,))

            return cursor.rowcount

    def close(self):
        """Close the database connection for this thread."""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            del self._local.connection
