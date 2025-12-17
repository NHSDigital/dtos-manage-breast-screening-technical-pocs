package dicom

import (
	"fmt"
	"sync"

	"go.uber.org/zap"
	"screening-gateway/internal/relay"
	"screening-gateway/internal/storage"
)

// MPPSHandler handles Modality Performed Procedure Step (MPPS) N-CREATE and N-SET requests
type MPPSHandler struct {
	storage          *storage.WorklistStorage
	relaySender      *relay.Sender // Optional - for sending events to Django
	logger           *zap.Logger
	managedInstances map[string]*MPPSInstance // SOPInstanceUID -> MPPS instance
	mu               sync.RWMutex
}

// MPPSInstance represents a managed MPPS instance
type MPPSInstance struct {
	SOPInstanceUID    string
	AccessionNumber   string
	StudyInstanceUID  string
	Modality          string
	Status            string
}

// NewMPPSHandler creates a new MPPS handler
// relaySender can be nil if relay communication is not configured
func NewMPPSHandler(worklistStorage *storage.WorklistStorage, relaySender *relay.Sender, logger *zap.Logger) *MPPSHandler {
	return &MPPSHandler{
		storage:          worklistStorage,
		relaySender:      relaySender,
		logger:           logger,
		managedInstances: make(map[string]*MPPSInstance),
	}
}

// HandleNCreate handles an MPPS N-CREATE request (procedure start)
// Returns success status and error if any
// Matches Python handle_create() behavior
func (h *MPPSHandler) HandleNCreate(
	sopInstanceUID string,
	status string,
	accessionNumber string,
	studyInstanceUID string,
	modality string,
) (bool, error) {
	h.mu.Lock()
	defer h.mu.Unlock()

	h.logger.Info("MPPS N-CREATE: Starting procedure",
		zap.String("accession_number", accessionNumber),
		zap.String("study_instance_uid", studyInstanceUID),
		zap.String("modality", modality),
		zap.String("sop_instance_uid", sopInstanceUID),
	)

	// Validate SOP Instance UID
	if sopInstanceUID == "" {
		h.logger.Error("MPPS N-CREATE: Missing SOP Instance UID")
		return false, fmt.Errorf("missing SOP Instance UID")
	}

	// Check for duplicate (Python returns 0x0111 for duplicate)
	if _, exists := h.managedInstances[sopInstanceUID]; exists {
		h.logger.Error("MPPS N-CREATE: Duplicate SOP Instance",
			zap.String("sop_instance_uid", sopInstanceUID),
		)
		return false, fmt.Errorf("duplicate SOP Instance UID")
	}

	// Validate status must be "IN PROGRESS"
	if status != storage.WorklistStatusInProgress {
		h.logger.Error("MPPS N-CREATE: Invalid status, must be IN PROGRESS",
			zap.String("status", status),
		)
		return false, fmt.Errorf("status must be IN PROGRESS for N-CREATE")
	}

	// Add to managed instances
	h.managedInstances[sopInstanceUID] = &MPPSInstance{
		SOPInstanceUID:   sopInstanceUID,
		AccessionNumber:  accessionNumber,
		StudyInstanceUID: studyInstanceUID,
		Modality:         modality,
		Status:           status,
	}

	// Update database
	if accessionNumber != "" && accessionNumber != "UNKNOWN" {
		sourceMessageID, err := h.storage.UpdateStatus(
			accessionNumber,
			status,
			&sopInstanceUID,
		)

		if err != nil {
			h.logger.Error("MPPS N-CREATE: Failed to update database",
				zap.String("accession_number", accessionNumber),
				zap.Error(err),
			)
			// Remove from managed instances on DB error
			delete(h.managedInstances, sopInstanceUID)
			return false, fmt.Errorf("failed to update database: %w", err)
		}

		if sourceMessageID == "" {
			h.logger.Warn("MPPS N-CREATE: Accession number not found in database",
				zap.String("accession_number", accessionNumber),
			)
			// Continue anyway - not a failure
		} else {
			h.logger.Info("MPPS N-CREATE: Database updated",
				zap.String("accession_number", accessionNumber),
				zap.String("status", status),
				zap.String("source_message_id", sourceMessageID),
			)

			// Send MPPS event to Django via Azure Relay
			if h.relaySender != nil {
				if err := h.relaySender.SendMPPSEventSync(
					sourceMessageID,
					accessionNumber,
					status,
					&sopInstanceUID,
				); err != nil {
					// Log error but don't fail the procedure
					// The MPPS operation itself succeeded
					h.logger.Error("MPPS N-CREATE: Failed to send relay event (procedure succeeded)",
						zap.String("accession_number", accessionNumber),
						zap.String("source_message_id", sourceMessageID),
						zap.Error(err),
					)
				} else {
					h.logger.Info("MPPS N-CREATE: Relay event sent successfully",
						zap.String("accession_number", accessionNumber),
						zap.String("source_message_id", sourceMessageID),
					)
				}
			} else {
				h.logger.Debug("MPPS N-CREATE: Relay sender not configured, skipping event")
			}
		}
	}

	h.logger.Info("MPPS N-CREATE: Success")
	return true, nil
}

// HandleNSet handles an MPPS N-SET request (procedure completion/discontinuation)
// Returns success status and error if any
// Matches Python handle_set() behavior
func (h *MPPSHandler) HandleNSet(
	sopInstanceUID string,
	status string,
) (bool, error) {
	h.mu.Lock()
	defer h.mu.Unlock()

	h.logger.Info("MPPS N-SET: Updating procedure status",
		zap.String("sop_instance_uid", sopInstanceUID),
		zap.String("status", status),
	)

	// Check if SOP Instance is managed
	instance, exists := h.managedInstances[sopInstanceUID]
	if !exists {
		h.logger.Warn("MPPS N-SET: SOP Instance not found in managed instances",
			zap.String("sop_instance_uid", sopInstanceUID),
		)
		return false, fmt.Errorf("SOP Instance UID not recognized")
	}

	accessionNumber := instance.AccessionNumber

	// Update database
	if accessionNumber != "" && accessionNumber != "UNKNOWN" {
		sourceMessageID, err := h.storage.UpdateStatus(
			accessionNumber,
			status,
			nil, // Don't update MPPS UID on N-SET
		)

		if err != nil {
			h.logger.Error("MPPS N-SET: Failed to update database",
				zap.String("accession_number", accessionNumber),
				zap.Error(err),
			)
			return false, fmt.Errorf("failed to update database: %w", err)
		}

		if sourceMessageID == "" {
			h.logger.Warn("MPPS N-SET: Accession number not found in database",
				zap.String("accession_number", accessionNumber),
			)
		} else {
			h.logger.Info("MPPS N-SET: Database updated",
				zap.String("accession_number", accessionNumber),
				zap.String("status", status),
				zap.String("source_message_id", sourceMessageID),
			)

			// Send MPPS event to Django via Azure Relay
			if h.relaySender != nil {
				if err := h.relaySender.SendMPPSEventSync(
					sourceMessageID,
					accessionNumber,
					status,
					nil, // MPPS UID not updated on N-SET
				); err != nil {
					// Log error but don't fail the procedure
					// The MPPS operation itself succeeded
					h.logger.Error("MPPS N-SET: Failed to send relay event (procedure succeeded)",
						zap.String("accession_number", accessionNumber),
						zap.String("source_message_id", sourceMessageID),
						zap.Error(err),
					)
				} else {
					h.logger.Info("MPPS N-SET: Relay event sent successfully",
						zap.String("accession_number", accessionNumber),
						zap.String("source_message_id", sourceMessageID),
					)
				}
			} else {
				h.logger.Debug("MPPS N-SET: Relay sender not configured, skipping event")
			}
		}
	}

	// Update managed instance
	instance.Status = status

	h.logger.Info("MPPS N-SET: Success")
	return true, nil
}

// GetManagedInstance returns a managed MPPS instance by SOP Instance UID
func (h *MPPSHandler) GetManagedInstance(sopInstanceUID string) (*MPPSInstance, bool) {
	h.mu.RLock()
	defer h.mu.RUnlock()

	instance, exists := h.managedInstances[sopInstanceUID]
	return instance, exists
}

// NOTE: The actual DICOM MPPS networking implementation will need to:
// 1. Parse incoming DICOM N-CREATE requests to extract:
//    - AffectedSOPInstanceUID
//    - PerformedProcedureStepStatus (must be "IN PROGRESS")
//    - ScheduledStepAttributesSequence (for accession number, study UID)
//    - Modality
// 2. Call HandleNCreate() with extracted parameters
// 3. Build and return DICOM N-CREATE response dataset
//
// 4. Parse incoming DICOM N-SET requests to extract:
//    - RequestedSOPInstanceUID
//    - PerformedProcedureStepStatus (COMPLETED or DISCONTINUED)
// 5. Call HandleNSet() with extracted parameters
// 6. Build and return DICOM N-SET response dataset
//
// This requires integration with a DICOM networking library that supports
// Service Class Provider (SCP) functionality for MPPS.
