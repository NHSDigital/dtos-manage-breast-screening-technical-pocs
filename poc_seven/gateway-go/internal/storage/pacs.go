package storage

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"

	_ "modernc.org/sqlite"
)

// PACSStorage provides thread-safe SQLite storage for DICOM images.
// Uses hash-based directory structure and Write-Ahead Logging (WAL) mode.
type PACSStorage struct {
	db          *sql.DB
	dbPath      string
	storageRoot string
	mu          sync.RWMutex // For file operations
}

// NewPACSStorage creates a new PACS storage instance.
// The database schema must already be initialized (see scripts/init_pacs_db.sql).
func NewPACSStorage(dbPath, storageRoot string) (*PACSStorage, error) {
	// Ensure directories exist
	if err := os.MkdirAll(filepath.Dir(dbPath), 0755); err != nil {
		return nil, fmt.Errorf("failed to create database directory: %w", err)
	}
	if err := os.MkdirAll(storageRoot, 0755); err != nil {
		return nil, fmt.Errorf("failed to create storage root: %w", err)
	}

	// Open database connection
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	// Configure connection pool (Go handles threading better than Python)
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(time.Hour)

	// Enable WAL mode for better concurrent access (matches Python)
	if _, err := db.Exec("PRAGMA journal_mode=WAL"); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to enable WAL mode: %w", err)
	}
	if _, err := db.Exec("PRAGMA synchronous=NORMAL"); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to set synchronous mode: %w", err)
	}

	return &PACSStorage{
		db:          db,
		dbPath:      dbPath,
		storageRoot: storageRoot,
	}, nil
}

// StoreInstance stores a DICOM instance with metadata.
// Returns the absolute path where the file was stored.
// Matches Python implementation exactly.
func (p *PACSStorage) StoreInstance(
	sopInstanceUID string,
	fileData []byte,
	metadata *StoredInstance,
	sourceAET string,
) (string, error) {
	p.mu.Lock()
	defer p.mu.Unlock()

	// Check if already exists
	exists, err := p.InstanceExists(sopInstanceUID)
	if err != nil {
		return "", err
	}
	if exists {
		return "", fmt.Errorf("instance already exists: %s", sopInstanceUID)
	}

	// Compute storage path using hash
	relPath := ComputeStoragePath(sopInstanceUID)
	absPath := filepath.Join(p.storageRoot, relPath)

	// Create directory
	if err := os.MkdirAll(filepath.Dir(absPath), 0755); err != nil {
		return "", fmt.Errorf("failed to create directory: %w", err)
	}

	// Write file
	if err := os.WriteFile(absPath, fileData, 0644); err != nil {
		return "", fmt.Errorf("failed to write file: %w", err)
	}

	// Compute file hash for integrity
	storageHash := ComputeFileHash(fileData)
	fileSize := int64(len(fileData))

	// Store metadata in database
	query := `
		INSERT INTO stored_instances (
			sop_instance_uid, storage_path, file_size, storage_hash,
			patient_id, patient_name,
			study_instance_uid, series_instance_uid,
			accession_number, study_date, study_time, study_description,
			series_number, series_description, modality,
			instance_number,
			view_position, laterality,
			organ_dose, entrance_dose_in_mgy, kvp, exposure_in_uas,
			anode_target_material, filter_material, filter_thickness,
			transfer_syntax_uid, sop_class_uid,
			rows, columns,
			source_aet, status
		) VALUES (
			?, ?, ?, ?,
			?, ?,
			?, ?,
			?, ?, ?, ?,
			?, ?, ?,
			?,
			?, ?,
			?, ?, ?, ?,
			?, ?, ?,
			?, ?,
			?, ?,
			?, 'STORED'
		)
	`

	_, err = p.db.Exec(query,
		sopInstanceUID, relPath, fileSize, storageHash,
		metadata.PatientID,
		metadata.PatientName,
		metadata.StudyInstanceUID,
		metadata.SeriesInstanceUID,
		metadata.AccessionNumber,
		metadata.StudyDate,
		metadata.StudyTime,
		metadata.StudyDescription,
		metadata.SeriesNumber,
		metadata.SeriesDescription,
		metadata.Modality,
		metadata.InstanceNumber,
		metadata.ViewPosition,
		metadata.Laterality,
		metadata.OrganDose,
		metadata.EntranceDoseInMgy,
		metadata.KVP,
		metadata.ExposureInUas,
		metadata.AnodeTargetMaterial,
		metadata.FilterMaterial,
		metadata.FilterThickness,
		metadata.TransferSyntaxUID,
		metadata.SOPClassUID,
		metadata.Rows,
		metadata.Columns,
		sourceAET,
	)

	if err != nil {
		// Clean up file if database insert fails
		os.Remove(absPath)
		return "", fmt.Errorf("failed to insert metadata: %w", err)
	}

	return absPath, nil
}

// InstanceExists checks if an instance exists in the database.
func (p *PACSStorage) InstanceExists(sopInstanceUID string) (bool, error) {
	query := "SELECT 1 FROM stored_instances WHERE sop_instance_uid = ? AND status = 'STORED'"

	var exists int
	err := p.db.QueryRow(query, sopInstanceUID).Scan(&exists)
	if err == sql.ErrNoRows {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("failed to check instance existence: %w", err)
	}

	return true, nil
}

// GetInstancePath returns the absolute path for a stored instance.
// Returns empty string if not found.
func (p *PACSStorage) GetInstancePath(sopInstanceUID string) (string, error) {
	query := "SELECT storage_path FROM stored_instances WHERE sop_instance_uid = ? AND status = 'STORED'"

	var storagePath string
	err := p.db.QueryRow(query, sopInstanceUID).Scan(&storagePath)
	if err == sql.ErrNoRows {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("failed to get instance path: %w", err)
	}

	return filepath.Join(p.storageRoot, storagePath), nil
}

// FindInstances finds instances matching the given criteria.
// Returns a slice of StoredInstance structs.
func (p *PACSStorage) FindInstances(
	patientID *string,
	studyUID *string,
	seriesUID *string,
	accessionNumber *string,
	modality *string,
	limit int,
) ([]*StoredInstance, error) {
	query := "SELECT * FROM stored_instances WHERE status = 'STORED'"
	args := []interface{}{}

	if patientID != nil {
		query += " AND patient_id = ?"
		args = append(args, *patientID)
	}

	if studyUID != nil {
		query += " AND study_instance_uid = ?"
		args = append(args, *studyUID)
	}

	if seriesUID != nil {
		query += " AND series_instance_uid = ?"
		args = append(args, *seriesUID)
	}

	if accessionNumber != nil {
		query += " AND accession_number = ?"
		args = append(args, *accessionNumber)
	}

	if modality != nil {
		query += " AND modality = ?"
		args = append(args, *modality)
	}

	query += " ORDER BY received_at DESC LIMIT ?"
	args = append(args, limit)

	rows, err := p.db.Query(query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to find instances: %w", err)
	}
	defer rows.Close()

	var instances []*StoredInstance
	for rows.Next() {
		instance := &StoredInstance{}
		err := rows.Scan(
			&instance.SOPInstanceUID,
			&instance.StoragePath,
			&instance.FileSize,
			&instance.StorageHash,
			&instance.PatientID,
			&instance.PatientName,
			&instance.StudyInstanceUID,
			&instance.SeriesInstanceUID,
			&instance.AccessionNumber,
			&instance.StudyDate,
			&instance.StudyTime,
			&instance.StudyDescription,
			&instance.SeriesNumber,
			&instance.SeriesDescription,
			&instance.Modality,
			&instance.InstanceNumber,
			&instance.ViewPosition,
			&instance.Laterality,
			&instance.OrganDose,
			&instance.EntranceDoseInMgy,
			&instance.KVP,
			&instance.ExposureInUas,
			&instance.AnodeTargetMaterial,
			&instance.FilterMaterial,
			&instance.FilterThickness,
			&instance.TransferSyntaxUID,
			&instance.SOPClassUID,
			&instance.Rows,
			&instance.Columns,
			&instance.ReceivedAt,
			&instance.SourceAET,
			&instance.Status,
			&instance.ThumbnailStatus,
			&instance.ThumbnailGeneratedAt,
			&instance.ThumbnailError,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan instance: %w", err)
		}
		instances = append(instances, instance)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating instances: %w", err)
	}

	return instances, nil
}

// GetPendingThumbnails returns instances that need thumbnail generation.
// Ordered by received_at to process oldest first.
func (p *PACSStorage) GetPendingThumbnails(limit int) ([]*StoredInstance, error) {
	query := `
		SELECT * FROM stored_instances
		WHERE status = 'STORED' AND thumbnail_status = 'PENDING'
		ORDER BY received_at ASC
		LIMIT ?
	`

	rows, err := p.db.Query(query, limit)
	if err != nil {
		return nil, fmt.Errorf("failed to get pending thumbnails: %w", err)
	}
	defer rows.Close()

	var instances []*StoredInstance
	for rows.Next() {
		instance := &StoredInstance{}
		err := rows.Scan(
			&instance.SOPInstanceUID,
			&instance.StoragePath,
			&instance.FileSize,
			&instance.StorageHash,
			&instance.PatientID,
			&instance.PatientName,
			&instance.StudyInstanceUID,
			&instance.SeriesInstanceUID,
			&instance.AccessionNumber,
			&instance.StudyDate,
			&instance.StudyTime,
			&instance.StudyDescription,
			&instance.SeriesNumber,
			&instance.SeriesDescription,
			&instance.Modality,
			&instance.InstanceNumber,
			&instance.ViewPosition,
			&instance.Laterality,
			&instance.OrganDose,
			&instance.EntranceDoseInMgy,
			&instance.KVP,
			&instance.ExposureInUas,
			&instance.AnodeTargetMaterial,
			&instance.FilterMaterial,
			&instance.FilterThickness,
			&instance.TransferSyntaxUID,
			&instance.SOPClassUID,
			&instance.Rows,
			&instance.Columns,
			&instance.ReceivedAt,
			&instance.SourceAET,
			&instance.Status,
			&instance.ThumbnailStatus,
			&instance.ThumbnailGeneratedAt,
			&instance.ThumbnailError,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan instance: %w", err)
		}
		instances = append(instances, instance)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating instances: %w", err)
	}

	return instances, nil
}

// UpdateThumbnailStatus updates the thumbnail status for an instance.
// This is called after thumbnail generation succeeds or fails.
func (p *PACSStorage) UpdateThumbnailStatus(
	sopInstanceUID string,
	status string,
	errorMsg *string,
) error {
	query := `
		UPDATE stored_instances
		SET thumbnail_status = ?,
			thumbnail_generated_at = CURRENT_TIMESTAMP,
			thumbnail_error = ?
		WHERE sop_instance_uid = ?
	`

	_, err := p.db.Exec(query, status, errorMsg, sopInstanceUID)
	if err != nil {
		return fmt.Errorf("failed to update thumbnail status: %w", err)
	}

	return nil
}

// GetStatistics returns storage statistics.
// Returns total instances, studies, patients, and size.
func (p *PACSStorage) GetStatistics() (map[string]interface{}, error) {
	query := `
		SELECT
			COUNT(*) as total_instances,
			COUNT(DISTINCT study_instance_uid) as total_studies,
			COUNT(DISTINCT patient_id) as total_patients,
			SUM(file_size) as total_size
		FROM stored_instances
		WHERE status = 'STORED'
	`

	var totalInstances, totalStudies, totalPatients int
	var totalSize sql.NullInt64

	err := p.db.QueryRow(query).Scan(&totalInstances, &totalStudies, &totalPatients, &totalSize)
	if err != nil {
		return nil, fmt.Errorf("failed to get statistics: %w", err)
	}

	stats := map[string]interface{}{
		"total_instances": totalInstances,
		"total_studies":   totalStudies,
		"total_patients":  totalPatients,
		"total_size":      totalSize.Int64,
	}

	return stats, nil
}

// Close closes the database connection.
func (p *PACSStorage) Close() error {
	return p.db.Close()
}
