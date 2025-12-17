package storage

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"time"

	_ "modernc.org/sqlite"
)

// WorklistStorage provides thread-safe SQLite storage for DICOM worklist items.
// Uses Write-Ahead Logging (WAL) mode for better concurrency.
type WorklistStorage struct {
	db     *sql.DB
	dbPath string
}

// NewWorklistStorage creates a new worklist storage instance.
// The database schema must already be initialized (see scripts/init_db.sql).
func NewWorklistStorage(dbPath string) (*WorklistStorage, error) {
	// Ensure database directory exists
	if err := os.MkdirAll(filepath.Dir(dbPath), 0755); err != nil {
		return nil, fmt.Errorf("failed to create database directory: %w", err)
	}

	// Open database connection
	// Note: Go's sql.DB is already thread-safe with connection pooling
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("failed to open database: %w", err)
	}

	// Configure connection pool
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

	return &WorklistStorage{
		db:     db,
		dbPath: dbPath,
	}, nil
}

// AddWorklistItem adds a new worklist item to the database.
// Returns the accession number on success.
func (w *WorklistStorage) AddWorklistItem(item *WorklistItem) error {
	query := `
		INSERT INTO worklist_items (
			accession_number, patient_id, patient_name, patient_birth_date,
			patient_sex, scheduled_date, scheduled_time, modality,
			study_description, procedure_code, study_instance_uid,
			source_message_id
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`

	_, err := w.db.Exec(query,
		item.AccessionNumber,
		item.PatientID,
		item.PatientName,
		item.PatientBirthDate,
		item.PatientSex,
		item.ScheduledDate,
		item.ScheduledTime,
		item.Modality,
		item.StudyDescription,
		item.ProcedureCode,
		item.StudyInstanceUID,
		item.SourceMessageID,
	)

	if err != nil {
		return fmt.Errorf("failed to insert worklist item: %w", err)
	}

	return nil
}

// FindWorklistItems queries worklist items with optional filters.
// Matches Python implementation exactly.
func (w *WorklistStorage) FindWorklistItems(
	modality *string,
	scheduledDate *string,
	patientID *string,
	status string,
) ([]*WorklistItem, error) {
	query := "SELECT * FROM worklist_items WHERE status = ?"
	args := []interface{}{status}

	if modality != nil {
		query += " AND modality = ?"
		args = append(args, *modality)
	}

	if scheduledDate != nil {
		query += " AND scheduled_date = ?"
		args = append(args, *scheduledDate)
	}

	if patientID != nil {
		query += " AND patient_id = ?"
		args = append(args, *patientID)
	}

	query += " ORDER BY scheduled_date, scheduled_time"

	rows, err := w.db.Query(query, args...)
	if err != nil {
		return nil, fmt.Errorf("failed to query worklist items: %w", err)
	}
	defer rows.Close()

	var items []*WorklistItem
	for rows.Next() {
		item := &WorklistItem{}
		err := rows.Scan(
			&item.AccessionNumber,
			&item.PatientID,
			&item.PatientName,
			&item.PatientBirthDate,
			&item.PatientSex,
			&item.ScheduledDate,
			&item.ScheduledTime,
			&item.Modality,
			&item.StudyDescription,
			&item.ProcedureCode,
			&item.Status,
			&item.StudyInstanceUID,
			&item.MPPSInstanceUID,
			&item.CreatedAt,
			&item.UpdatedAt,
			&item.SourceMessageID,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan worklist item: %w", err)
		}
		items = append(items, item)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating worklist items: %w", err)
	}

	return items, nil
}

// GetWorklistItem gets a single worklist item by accession number.
// Returns nil if not found.
func (w *WorklistStorage) GetWorklistItem(accessionNumber string) (*WorklistItem, error) {
	query := "SELECT * FROM worklist_items WHERE accession_number = ?"

	item := &WorklistItem{}
	err := w.db.QueryRow(query, accessionNumber).Scan(
		&item.AccessionNumber,
		&item.PatientID,
		&item.PatientName,
		&item.PatientBirthDate,
		&item.PatientSex,
		&item.ScheduledDate,
		&item.ScheduledTime,
		&item.Modality,
		&item.StudyDescription,
		&item.ProcedureCode,
		&item.Status,
		&item.StudyInstanceUID,
		&item.MPPSInstanceUID,
		&item.CreatedAt,
		&item.UpdatedAt,
		&item.SourceMessageID,
	)

	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("failed to get worklist item: %w", err)
	}

	return item, nil
}

// UpdateStatus updates the status of a worklist item.
// Returns the source_message_id if the item was updated, empty string if not found.
// Matches Python implementation exactly.
func (w *WorklistStorage) UpdateStatus(
	accessionNumber string,
	status string,
	mppsInstanceUID *string,
) (string, error) {
	tx, err := w.db.Begin()
	if err != nil {
		return "", fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback()

	// Update the item
	query := `
		UPDATE worklist_items
		SET status = ?,
			mpps_instance_uid = COALESCE(?, mpps_instance_uid),
			updated_at = CURRENT_TIMESTAMP
		WHERE accession_number = ?
	`

	result, err := tx.Exec(query, status, mppsInstanceUID, accessionNumber)
	if err != nil {
		return "", fmt.Errorf("failed to update status: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return "", fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return "", nil // Not found
	}

	// Fetch the source_message_id for the updated item
	var sourceMessageID sql.NullString
	err = tx.QueryRow(
		"SELECT source_message_id FROM worklist_items WHERE accession_number = ?",
		accessionNumber,
	).Scan(&sourceMessageID)

	if err != nil {
		return "", fmt.Errorf("failed to fetch source_message_id: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return "", fmt.Errorf("failed to commit transaction: %w", err)
	}

	if sourceMessageID.Valid {
		return sourceMessageID.String, nil
	}
	return "", nil
}

// UpdateStudyInstanceUID updates the study instance UID for a worklist item.
// Returns true if the item was updated, false if not found.
func (w *WorklistStorage) UpdateStudyInstanceUID(
	accessionNumber string,
	studyInstanceUID string,
) (bool, error) {
	query := `
		UPDATE worklist_items
		SET study_instance_uid = ?,
			updated_at = CURRENT_TIMESTAMP
		WHERE accession_number = ?
	`

	result, err := w.db.Exec(query, studyInstanceUID, accessionNumber)
	if err != nil {
		return false, fmt.Errorf("failed to update study instance UID: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return false, fmt.Errorf("failed to get rows affected: %w", err)
	}

	return rowsAffected > 0, nil
}

// DeleteWorklistItem deletes a worklist item.
// Returns true if the item was deleted, false if not found.
func (w *WorklistStorage) DeleteWorklistItem(accessionNumber string) (bool, error) {
	query := "DELETE FROM worklist_items WHERE accession_number = ?"

	result, err := w.db.Exec(query, accessionNumber)
	if err != nil {
		return false, fmt.Errorf("failed to delete worklist item: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return false, fmt.Errorf("failed to get rows affected: %w", err)
	}

	return rowsAffected > 0, nil
}

// GetStatistics returns statistics about worklist items.
// Returns a map of status -> count, plus a TOTAL key.
func (w *WorklistStorage) GetStatistics() (map[string]int, error) {
	query := `
		SELECT status, COUNT(*) as count
		FROM worklist_items
		GROUP BY status
	`

	rows, err := w.db.Query(query)
	if err != nil {
		return nil, fmt.Errorf("failed to get statistics: %w", err)
	}
	defer rows.Close()

	stats := make(map[string]int)
	total := 0

	for rows.Next() {
		var status string
		var count int
		if err := rows.Scan(&status, &count); err != nil {
			return nil, fmt.Errorf("failed to scan statistics: %w", err)
		}
		stats[status] = count
		total += count
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating statistics: %w", err)
	}

	stats["TOTAL"] = total

	return stats, nil
}

// CleanupOldItems deletes completed/discontinued worklist items older than specified days.
// Returns the number of items deleted.
func (w *WorklistStorage) CleanupOldItems(daysOld int) (int, error) {
	query := `
		DELETE FROM worklist_items
		WHERE datetime(created_at) < datetime('now', '-' || ? || ' days')
		AND status IN ('COMPLETED', 'DISCONTINUED')
	`

	result, err := w.db.Exec(query, daysOld)
	if err != nil {
		return 0, fmt.Errorf("failed to cleanup old items: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return 0, fmt.Errorf("failed to get rows affected: %w", err)
	}

	return int(rowsAffected), nil
}

// Close closes the database connection.
func (w *WorklistStorage) Close() error {
	return w.db.Close()
}
