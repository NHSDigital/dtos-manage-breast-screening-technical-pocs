package relay

import (
	"time"

	"github.com/google/uuid"
)

// MPPSEvent represents an MPPS status update event sent to Django
// Matches Python send_mpps_event() structure
type MPPSEvent struct {
	SchemaVersion int          `json:"schema_version"`
	EventType     string       `json:"event_type"`
	Timestamp     string       `json:"timestamp"`
	SourceSystem  string       `json:"source_system"`
	Data          MPPSEventData `json:"data"`
}

// MPPSEventData contains the MPPS event payload
type MPPSEventData struct {
	ActionID         string  `json:"action_id"`
	AccessionNumber  string  `json:"accession_number"`
	Status           string  `json:"status"`
	MPPSInstanceUID  *string `json:"mpps_instance_uid,omitempty"`
}

// NewMPPSEvent creates a new MPPS status update event
func NewMPPSEvent(actionID, accessionNumber, status string, mppsInstanceUID *string) *MPPSEvent {
	return &MPPSEvent{
		SchemaVersion: 1,
		EventType:     "mpps.status_update",
		Timestamp:     time.Now().UTC().Format("2006-01-02T15:04:05Z"),
		SourceSystem:  "gateway-mwl",
		Data: MPPSEventData{
			ActionID:        actionID,
			AccessionNumber: accessionNumber,
			Status:          status,
			MPPSInstanceUID: mppsInstanceUID,
		},
	}
}

// ImageReceivedMessage represents an image_received event sent to Django
// Matches Python build_image_received_message() structure
type ImageReceivedMessage struct{
	SchemaVersion   int                    `json:"schema_version"`
	MessageID       string                 `json:"message_id"`
	MessageType     string                 `json:"message_type"`
	Timestamp       string                 `json:"timestamp"`
	SourceSystem    string                 `json:"source_system"`
	SourceReference SourceReference        `json:"source_reference"`
	Parameters      ImageMessageParameters `json:"parameters"`
}

// SourceReference links the message back to the originating worklist action
type SourceReference struct {
	ActionID *string `json:"action_id,omitempty"`
}

// ImageMessageParameters contains the complete image metadata
type ImageMessageParameters struct {
	Participant ParticipantInfo `json:"participant"`
	Study       StudyInfo       `json:"study"`
	Series      SeriesInfo      `json:"series"`
	Image       ImageInfo       `json:"image"`
}

// ParticipantInfo contains patient demographics
type ParticipantInfo struct {
	NHSNumber   *string `json:"nhs_number,omitempty"`
	PatientName *string `json:"patient_name,omitempty"`
}

// StudyInfo contains study-level metadata
type StudyInfo struct {
	AccessionNumber  *string `json:"accession_number,omitempty"`
	StudyInstanceUID string  `json:"study_instance_uid"`
	Modality         *string `json:"modality,omitempty"`
	StudyDate        *string `json:"study_date,omitempty"`
	StudyTime        *string `json:"study_time,omitempty"`
	StudyDescription *string `json:"study_description,omitempty"`
}

// SeriesInfo contains series-level metadata
type SeriesInfo struct {
	SeriesInstanceUID  string  `json:"series_instance_uid"`
	SeriesNumber       *string `json:"series_number,omitempty"`
	SeriesDescription  *string `json:"series_description,omitempty"`
}

// ImageInfo contains instance-level metadata and thumbnail
type ImageInfo struct {
	SOPInstanceUID string           `json:"sop_instance_uid"`
	InstanceNumber *string          `json:"instance_number,omitempty"`
	Dimensions     *ImageDimensions `json:"dimensions,omitempty"`
	Acquisition    *ImageAcquisition `json:"acquisition,omitempty"`
	Dose           *DoseInformation `json:"dose,omitempty"`
	ReceivedAt     *string          `json:"received_at,omitempty"`
	Thumbnail      *ThumbnailInfo   `json:"thumbnail,omitempty"`
}

// ImageDimensions contains image dimensions
type ImageDimensions struct {
	Rows    *int64 `json:"rows,omitempty"`
	Columns *int64 `json:"columns,omitempty"`
}

// ImageAcquisition contains acquisition parameters
type ImageAcquisition struct {
	ViewPosition *string `json:"view_position,omitempty"`
	Laterality   *string `json:"laterality,omitempty"`
}

// DoseInformation contains mammography dose parameters
type DoseInformation struct {
	OrganDose            *string `json:"organ_dose,omitempty"`
	EntranceDoseInMgy    *string `json:"entrance_dose_in_mgy,omitempty"`
	KVP                  *string `json:"kvp,omitempty"`
	ExposureInUas        *string `json:"exposure_in_uas,omitempty"`
	AnodeTargetMaterial  *string `json:"anode_target_material,omitempty"`
	FilterMaterial       *string `json:"filter_material,omitempty"`
	FilterThickness      *string `json:"filter_thickness,omitempty"`
}

// ThumbnailInfo contains thumbnail data
type ThumbnailInfo struct {
	Data   string `json:"data"`   // Base64 encoded
	Format string `json:"format"` // "jpeg"
	Width  int    `json:"width"`
	Height int    `json:"height"`
}

// NewImageReceivedMessage creates a new image_received message
func NewImageReceivedMessage(actionID *string) *ImageReceivedMessage {
	return &ImageReceivedMessage{
		SchemaVersion: 1,
		MessageID:     uuid.New().String(),
		MessageType:   "study.image_received",
		Timestamp:     time.Now().UTC().Format("2006-01-02T15:04:05Z"),
		SourceSystem:  "gateway-pacs",
		SourceReference: SourceReference{
			ActionID: actionID,
		},
		Parameters: ImageMessageParameters{},
	}
}

// RelayResponse represents the acknowledgment response from Django
type RelayResponse struct {
	Status  string `json:"status"`
	Message string `json:"message,omitempty"`
}

// WorklistAction represents a worklist action received from Django
// (Used by relay-listener to create worklist items)
type WorklistAction struct {
	ActionType string                 `json:"action_type"`
	ActionID   string                 `json:"action_id"`
	Parameters WorklistActionParameters `json:"parameters"`
}

// WorklistActionParameters contains the worklist item details
type WorklistActionParameters struct {
	WorklistItem WorklistItemDetails `json:"worklist_item"`
}

// WorklistItemDetails contains all worklist item fields
type WorklistItemDetails struct {
	AccessionNumber string              `json:"accession_number"`
	Participant     WorklistParticipant `json:"participant"`
	Scheduled       WorklistSchedule    `json:"scheduled"`
	Procedure       WorklistProcedure   `json:"procedure"`
}

// WorklistParticipant contains patient details for worklist
type WorklistParticipant struct {
	NHSNumber string `json:"nhs_number"`
	Name      string `json:"name"`
	BirthDate string `json:"birth_date"`
	Sex       string `json:"sex"`
}

// WorklistSchedule contains scheduling information
type WorklistSchedule struct {
	Date string `json:"date"`
	Time string `json:"time"`
}

// WorklistProcedure contains procedure details
type WorklistProcedure struct {
	Modality         string `json:"modality"`
	StudyDescription string `json:"study_description"`
}
