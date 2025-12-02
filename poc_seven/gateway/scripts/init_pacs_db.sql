-- PACS Database Schema
-- Stores metadata and file paths for DICOM images

-- Main table for stored DICOM instances
CREATE TABLE IF NOT EXISTS stored_instances (
    -- Primary key: SOP Instance UID
    sop_instance_uid TEXT PRIMARY KEY,

    -- Storage information
    storage_path TEXT NOT NULL,           -- Relative path from storage root
    file_size INTEGER NOT NULL,           -- File size in bytes
    storage_hash TEXT NOT NULL,           -- Hash for file integrity checks

    -- DICOM hierarchy identifiers
    patient_id TEXT,
    patient_name TEXT,
    study_instance_uid TEXT NOT NULL,
    series_instance_uid TEXT NOT NULL,

    -- Study/Series level metadata
    accession_number TEXT,                -- Link to worklist
    study_date TEXT,                      -- YYYYMMDD format
    study_time TEXT,                      -- HHMMSS format
    study_description TEXT,

    series_number TEXT,
    series_description TEXT,
    modality TEXT NOT NULL,               -- MG, CT, MR, etc.

    -- Instance level metadata
    instance_number TEXT,

    -- Mammography specific metadata
    view_position TEXT,                   -- CC, MLO, etc.
    laterality TEXT,                      -- L, R

    -- Transfer syntax and image info
    transfer_syntax_uid TEXT,
    sop_class_uid TEXT NOT NULL,
    rows INTEGER,
    columns INTEGER,

    -- Audit trail
    received_at TEXT DEFAULT CURRENT_TIMESTAMP,
    source_aet TEXT,                      -- AE Title of sender

    -- Status tracking
    status TEXT DEFAULT 'STORED' CHECK(status IN ('STORED', 'ARCHIVED', 'DELETED')),

    -- Thumbnail tracking
    thumbnail_status TEXT DEFAULT 'PENDING' CHECK(thumbnail_status IN ('PENDING', 'GENERATED', 'FAILED', 'SKIP')),
    thumbnail_generated_at TEXT,
    thumbnail_error TEXT,

    UNIQUE(storage_path)
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_patient_id ON stored_instances(patient_id);
CREATE INDEX IF NOT EXISTS idx_study_uid ON stored_instances(study_instance_uid);
CREATE INDEX IF NOT EXISTS idx_series_uid ON stored_instances(series_instance_uid);
CREATE INDEX IF NOT EXISTS idx_accession_number ON stored_instances(accession_number);
CREATE INDEX IF NOT EXISTS idx_study_date ON stored_instances(study_date);
CREATE INDEX IF NOT EXISTS idx_modality ON stored_instances(modality);
CREATE INDEX IF NOT EXISTS idx_received_at ON stored_instances(received_at);
CREATE INDEX IF NOT EXISTS idx_storage_hash ON stored_instances(storage_hash);
CREATE INDEX IF NOT EXISTS idx_view_position ON stored_instances(view_position);
CREATE INDEX IF NOT EXISTS idx_laterality ON stored_instances(laterality);
CREATE INDEX IF NOT EXISTS idx_thumbnail_status ON stored_instances(thumbnail_status);

-- Study-level summary view (for faster study queries)
CREATE VIEW IF NOT EXISTS study_summary AS
SELECT
    study_instance_uid,
    patient_id,
    patient_name,
    accession_number,
    study_date,
    study_time,
    study_description,
    modality,
    COUNT(*) as image_count,
    SUM(file_size) as total_size,
    MIN(received_at) as first_received,
    MAX(received_at) as last_received
FROM stored_instances
WHERE status = 'STORED'
GROUP BY study_instance_uid;

-- Series-level summary view
CREATE VIEW IF NOT EXISTS series_summary AS
SELECT
    series_instance_uid,
    study_instance_uid,
    patient_id,
    series_number,
    series_description,
    modality,
    COUNT(*) as image_count,
    SUM(file_size) as total_size
FROM stored_instances
WHERE status = 'STORED'
GROUP BY series_instance_uid;

-- Statistics table for monitoring
CREATE TABLE IF NOT EXISTS storage_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    total_instances INTEGER,
    total_size_bytes INTEGER,
    total_studies INTEGER,
    total_series INTEGER
);

-- Trigger to update stats on insert
CREATE TRIGGER IF NOT EXISTS update_stats_on_insert
AFTER INSERT ON stored_instances
BEGIN
    INSERT INTO storage_stats (total_instances, total_size_bytes, total_studies, total_series)
    SELECT
        COUNT(*),
        SUM(file_size),
        COUNT(DISTINCT study_instance_uid),
        COUNT(DISTINCT series_instance_uid)
    FROM stored_instances
    WHERE status = 'STORED';
END;
