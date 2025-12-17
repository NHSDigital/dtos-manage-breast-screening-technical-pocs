package storage

import (
	"database/sql"
	"time"
)

// WorklistItem represents a DICOM worklist entry for a scheduled procedure
type WorklistItem struct {
	// Unique identifier
	AccessionNumber string `db:"accession_number"`

	// Patient demographics
	PatientID        string `db:"patient_id"`
	PatientName      string `db:"patient_name"`       // DICOM format: FAMILY^GIVEN
	PatientBirthDate string `db:"patient_birth_date"` // YYYYMMDD format
	PatientSex       string `db:"patient_sex"`        // M/F/O

	// Scheduling information
	ScheduledDate string `db:"scheduled_date"` // YYYYMMDD format
	ScheduledTime string `db:"scheduled_time"` // HHMMSS format
	Modality      string `db:"modality"`       // e.g., MG for mammography

	// Procedure details
	StudyDescription sql.NullString `db:"study_description"`
	ProcedureCode    sql.NullString `db:"procedure_code"`

	// Status tracking
	// SCHEDULED | IN_PROGRESS | COMPLETED | DISCONTINUED
	Status string `db:"status"`

	// DICOM identifiers
	StudyInstanceUID sql.NullString `db:"study_instance_uid"`
	MPPSInstanceUID  sql.NullString `db:"mpps_instance_uid"`

	// Audit trail
	CreatedAt time.Time `db:"created_at"`
	UpdatedAt time.Time `db:"updated_at"`

	// Link to source message from relay listener
	SourceMessageID sql.NullString `db:"source_message_id"`
}

// StoredInstance represents a DICOM image stored in the PACS
type StoredInstance struct {
	// Primary key
	SOPInstanceUID string `db:"sop_instance_uid"`

	// Storage information
	StoragePath  string `db:"storage_path"`   // Relative path from storage root
	FileSize     int64  `db:"file_size"`      // File size in bytes
	StorageHash  string `db:"storage_hash"`   // SHA256 hash for integrity

	// DICOM hierarchy identifiers
	PatientID        sql.NullString `db:"patient_id"`
	PatientName      sql.NullString `db:"patient_name"`
	StudyInstanceUID string         `db:"study_instance_uid"`
	SeriesInstanceUID string        `db:"series_instance_uid"`

	// Study/Series level metadata
	AccessionNumber   sql.NullString `db:"accession_number"` // Link to worklist
	StudyDate         sql.NullString `db:"study_date"`       // YYYYMMDD format
	StudyTime         sql.NullString `db:"study_time"`       // HHMMSS format
	StudyDescription  sql.NullString `db:"study_description"`
	SeriesNumber      sql.NullString `db:"series_number"`
	SeriesDescription sql.NullString `db:"series_description"`
	Modality          string         `db:"modality"` // MG, CT, MR, etc.

	// Instance level metadata
	InstanceNumber sql.NullString `db:"instance_number"`

	// Mammography specific metadata
	ViewPosition sql.NullString `db:"view_position"` // CC, MLO, etc.
	Laterality   sql.NullString `db:"laterality"`    // L, R

	// Dose and exposure parameters
	OrganDose            sql.NullString `db:"organ_dose"`             // Mean Glandular Dose (MGD) in mGy
	EntranceDoseInMgy    sql.NullString `db:"entrance_dose_in_mgy"`   // Entrance surface dose in mGy
	KVP                  sql.NullString `db:"kvp"`                    // Tube voltage in kV
	ExposureInUas        sql.NullString `db:"exposure_in_uas"`        // Tube current-time product in µAs
	AnodeTargetMaterial  sql.NullString `db:"anode_target_material"`  // e.g., TUNGSTEN
	FilterMaterial       sql.NullString `db:"filter_material"`        // e.g., RHODIUM
	FilterThickness      sql.NullString `db:"filter_thickness"`       // Filter thickness in mm

	// Transfer syntax and image info
	TransferSyntaxUID sql.NullString `db:"transfer_syntax_uid"`
	SOPClassUID       string         `db:"sop_class_uid"`
	Rows              sql.NullInt64  `db:"rows"`
	Columns           sql.NullInt64  `db:"columns"`

	// Audit trail
	ReceivedAt time.Time      `db:"received_at"`
	SourceAET  sql.NullString `db:"source_aet"` // AE Title of sender

	// Status tracking
	Status string `db:"status"` // STORED | ARCHIVED | DELETED

	// Thumbnail tracking
	ThumbnailStatus      string         `db:"thumbnail_status"` // PENDING | GENERATED | FAILED | SKIP
	ThumbnailGeneratedAt sql.NullTime   `db:"thumbnail_generated_at"`
	ThumbnailError       sql.NullString `db:"thumbnail_error"`
}

// WorklistStatus constants
const (
	WorklistStatusScheduled     = "SCHEDULED"
	WorklistStatusInProgress    = "IN PROGRESS"
	WorklistStatusCompleted     = "COMPLETED"
	WorklistStatusDiscontinued  = "DISCONTINUED"
)

// InstanceStatus constants
const (
	InstanceStatusStored   = "STORED"
	InstanceStatusArchived = "ARCHIVED"
	InstanceStatusDeleted  = "DELETED"
)

// ThumbnailStatus constants
const (
	ThumbnailStatusPending   = "PENDING"
	ThumbnailStatusGenerated = "GENERATED"
	ThumbnailStatusFailed    = "FAILED"
	ThumbnailStatusSkip      = "SKIP"
)

// NewNullString creates a sql.NullString from a string
// Returns Valid=false if string is empty
func NewNullString(s string) sql.NullString {
	if s == "" {
		return sql.NullString{Valid: false}
	}
	return sql.NullString{String: s, Valid: true}
}
