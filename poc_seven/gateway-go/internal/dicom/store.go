package dicom

import (
	"bytes"
	"database/sql"
	"fmt"
	"io"

	"github.com/suyashkumar/dicom"
	"go.uber.org/zap"
	"screening-gateway/internal/storage"
)

// StoreHandler handles C-STORE requests for receiving DICOM images
type StoreHandler struct {
	storage *storage.PACSStorage
	logger  *zap.Logger
}

// NewStoreHandler creates a new C-STORE handler
func NewStoreHandler(pacsStorage *storage.PACSStorage, logger *zap.Logger) *StoreHandler {
	return &StoreHandler{
		storage: pacsStorage,
		logger:  logger,
	}
}

// HandleStore processes a C-STORE request
// Returns true if successful, false if failed
// Matches Python handle_store() behavior
func (h *StoreHandler) HandleStore(fileData []byte, sourceAET string) (bool, error) {
	h.logger.Debug("Processing C-STORE request",
		zap.Int("size", len(fileData)),
		zap.String("source_aet", sourceAET),
	)

	// Parse DICOM dataset
	dataset, err := dicom.Parse(bytes.NewReader(fileData), int64(len(fileData)), nil)
	if err != nil {
		h.logger.Error("Failed to parse DICOM dataset", zap.Error(err))
		return false, fmt.Errorf("failed to parse DICOM: %w", err)
	}

	// Extract metadata
	metadata, err := ExtractMetadata(&dataset)
	if err != nil {
		h.logger.Error("Failed to extract metadata", zap.Error(err))
		return false, fmt.Errorf("failed to extract metadata: %w", err)
	}

	sopInstanceUID := metadata.SOPInstanceUID
	if sopInstanceUID == "" {
		h.logger.Error("Missing SOP Instance UID")
		return false, fmt.Errorf("missing SOP Instance UID")
	}

	// Check if instance already exists (idempotent behavior like Python)
	exists, err := h.storage.InstanceExists(sopInstanceUID)
	if err != nil {
		h.logger.Error("Failed to check instance existence",
			zap.String("sop_instance_uid", sopInstanceUID),
			zap.Error(err),
		)
		return false, err
	}

	if exists {
		h.logger.Info("Instance already exists (idempotent success)",
			zap.String("sop_instance_uid", sopInstanceUID),
		)
		return true, nil // Return success (idempotent like Python)
	}

	// Store the instance
	absPath, err := h.storage.StoreInstance(sopInstanceUID, fileData, metadata, sourceAET)
	if err != nil {
		h.logger.Error("Failed to store instance",
			zap.String("sop_instance_uid", sopInstanceUID),
			zap.Error(err),
		)
		return false, err
	}

	// Log success with details (matches Python logging)
	h.logger.Info("Stored instance",
		zap.String("sop_instance_uid", sopInstanceUID),
		zap.String("path", absPath),
	)
	h.logger.Info("  Patient",
		zap.String("patient_id", getNullString(metadata.PatientID)),
		zap.String("patient_name", getNullString(metadata.PatientName)),
	)
	h.logger.Info("  Study",
		zap.String("study_instance_uid", metadata.StudyInstanceUID),
	)
	h.logger.Info("  Metadata",
		zap.String("modality", metadata.Modality),
		zap.String("accession", getNullString(metadata.AccessionNumber)),
	)

	return true, nil
}

// HandleStoreFromReader processes a C-STORE request from an io.Reader
// Useful for streaming DICOM data from network
func (h *StoreHandler) HandleStoreFromReader(reader io.Reader, sourceAET string) (bool, error) {
	// Read all data into memory
	fileData, err := io.ReadAll(reader)
	if err != nil {
		h.logger.Error("Failed to read DICOM data", zap.Error(err))
		return false, fmt.Errorf("failed to read DICOM data: %w", err)
	}

	return h.HandleStore(fileData, sourceAET)
}

// getNullString safely extracts string from sql.NullString
func getNullString(ns sql.NullString) string {
	if ns.Valid {
		return ns.String
	}
	return ""
}
