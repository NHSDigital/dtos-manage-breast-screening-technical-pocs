import logging
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class Storage:
    def __init__(self, db_path: str, schema_path: str, table_name: str):
        self.db_path = db_path
        self.schema_path = schema_path
        self.table_name = table_name
        self._ensure_db()

        with self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.commit()

    @contextmanager
    def _get_connection(self):
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            if conn:
                conn.close()

    def _ensure_db(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        with self._get_connection() as conn:
            cursor = conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{self.table_name}'")
            if cursor.fetchone() is None:
                logger.info(f"Initializing database schema from {self.schema_path}")
                conn.executescript(Path(self.schema_path).read_text())
                conn.commit()


@dataclass
class WorklistItem:
    accession_number: str
    modality: str
    patient_birth_date: str
    patient_id: str
    patient_name: str
    scheduled_date: str
    scheduled_time: str
    status: str = "SCHEDULED"
    source_message_id: Optional[str] = None
    study_instance_uid: Optional[str] = None
    procedure_code: Optional[str] = None
    patient_sex: Optional[str] = None
    study_description: Optional[str] = None
    mpps_instance_uid: Optional[str] = None


class MWLStorage(Storage):
    def __init__(self, db_path: str = "./data/worklist.db"):
        super().__init__(db_path, f"{Path(__file__).parent}/init_worklist_db.sql", "worklist_items")
        logger.info(f"Worklist storage initialized: db={db_path}")

    def store_worklist_item(self, worklist_item: WorklistItem) -> str:
        with self._get_connection() as conn:
            conn.execute(
                (
                    "INSERT INTO worklist_items (accession_number, modality, patient_birth_date, "
                    "patient_id, patient_name, patient_sex, procedure_code, scheduled_date, "
                    "scheduled_time, source_message_id, study_description, study_instance_uid) "
                    "VALUES (:accession_number, :modality, :patient_birth_date, "
                    ":patient_id, :patient_name, :patient_sex, :procedure_code, "
                    ":scheduled_date, :scheduled_time, :source_message_id, "
                    ":study_description, :study_instance_uid)"
                ),
                worklist_item.__dict__,
            )
            conn.commit()

        return worklist_item.accession_number

    def get_worklist_item(self, accession_number: str) -> Optional[WorklistItem]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                (
                    "SELECT accession_number, modality, patient_birth_date, patient_id, "
                    "patient_name, patient_sex, procedure_code, scheduled_date, scheduled_time, "
                    "source_message_id, study_description, study_instance_uid, status, mpps_instance_uid "
                    "FROM worklist_items WHERE accession_number = ?"
                ),
                (accession_number,),
            )
            row = cursor.fetchone()

        return WorklistItem(**row) if row else None
