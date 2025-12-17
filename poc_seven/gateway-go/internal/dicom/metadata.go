package dicom

import (
	"database/sql"
	"fmt"

	"github.com/suyashkumar/dicom"
	"github.com/suyashkumar/dicom/pkg/tag"
	"screening-gateway/internal/storage"
)

// ExtractMetadata extracts DICOM metadata from a dataset and populates a StoredInstance.
// Matches the Python implementation in pacs_server.py handle_store().
func ExtractMetadata(dataset *dicom.Dataset) (*storage.StoredInstance, error) {
	instance := &storage.StoredInstance{}

	// Required fields
	sopInstanceUID, err := dataset.FindElementByTag(tag.SOPInstanceUID)
	if err != nil || sopInstanceUID == nil {
		return nil, fmt.Errorf("missing SOPInstanceUID: %w", err)
	}
	instance.SOPInstanceUID = getString(sopInstanceUID)

	studyInstanceUID, err := dataset.FindElementByTag(tag.StudyInstanceUID)
	if err != nil || studyInstanceUID == nil {
		return nil, fmt.Errorf("missing StudyInstanceUID: %w", err)
	}
	instance.StudyInstanceUID = getString(studyInstanceUID)

	seriesInstanceUID, err := dataset.FindElementByTag(tag.SeriesInstanceUID)
	if err != nil || seriesInstanceUID == nil {
		return nil, fmt.Errorf("missing SeriesInstanceUID: %w", err)
	}
	instance.SeriesInstanceUID = getString(seriesInstanceUID)

	sopClassUID, err := dataset.FindElementByTag(tag.SOPClassUID)
	if err != nil || sopClassUID == nil {
		return nil, fmt.Errorf("missing SOPClassUID: %w", err)
	}
	instance.SOPClassUID = getString(sopClassUID)

	modality, err := dataset.FindElementByTag(tag.Modality)
	if err != nil || modality == nil {
		return nil, fmt.Errorf("missing Modality: %w", err)
	}
	instance.Modality = getString(modality)

	// Patient demographics (nullable)
	instance.PatientID = getStringOptional(dataset, tag.PatientID)
	instance.PatientName = getStringOptional(dataset, tag.PatientName)

	// Study/Series level metadata
	instance.AccessionNumber = getStringOptional(dataset, tag.AccessionNumber)
	instance.StudyDate = getStringOptional(dataset, tag.StudyDate)
	instance.StudyTime = getStringOptional(dataset, tag.StudyTime)
	instance.StudyDescription = getStringOptional(dataset, tag.StudyDescription)
	instance.SeriesNumber = getStringOptional(dataset, tag.SeriesNumber)
	instance.SeriesDescription = getStringOptional(dataset, tag.SeriesDescription)

	// Instance level metadata
	instance.InstanceNumber = getStringOptional(dataset, tag.InstanceNumber)

	// Mammography specific metadata
	instance.ViewPosition = getStringOptional(dataset, tag.ViewPosition)

	// Laterality - try ImageLaterality first, then Laterality
	laterality := getStringOptional(dataset, tag.ImageLaterality)
	if !laterality.Valid || laterality.String == "" {
		laterality = getStringOptional(dataset, tag.Laterality)
	}
	instance.Laterality = laterality

	// Dose and exposure parameters (mammography specific)
	instance.OrganDose = getStringOptional(dataset, tag.OrganDose)
	instance.EntranceDoseInMgy = getStringOptional(dataset, tag.EntranceDoseInmGy)
	instance.KVP = getStringOptional(dataset, tag.KVP)
	instance.ExposureInUas = getStringOptional(dataset, tag.ExposureInuAs)
	instance.AnodeTargetMaterial = getStringOptional(dataset, tag.AnodeTargetMaterial)
	instance.FilterMaterial = getStringOptional(dataset, tag.FilterMaterial)
	instance.FilterThickness = getStringOptional(dataset, tag.FilterThicknessMinimum)

	// Transfer syntax (from file meta)
	instance.TransferSyntaxUID = getStringOptional(dataset, tag.TransferSyntaxUID)

	// Image dimensions
	instance.Rows = getIntOptional(dataset, tag.Rows)
	instance.Columns = getIntOptional(dataset, tag.Columns)

	return instance, nil
}

// getString extracts a string value from a DICOM element (required field)
func getString(elem *dicom.Element) string {
	if elem == nil {
		return ""
	}

	value := elem.Value
	if value == nil {
		return ""
	}

	// Handle string values
	if str, ok := value.GetValue().(string); ok {
		return str
	}

	// Handle string slice (take first value)
	if strs, ok := value.GetValue().([]string); ok && len(strs) > 0 {
		return strs[0]
	}

	// Fallback: convert to string
	return fmt.Sprintf("%v", value.GetValue())
}

// getStringOptional extracts an optional string value from a DICOM dataset
func getStringOptional(dataset *dicom.Dataset, tagInfo tag.Tag) sql.NullString {
	elem, err := dataset.FindElementByTag(tagInfo)
	if err != nil || elem == nil {
		return sql.NullString{Valid: false}
	}

	str := getString(elem)
	if str == "" {
		return sql.NullString{Valid: false}
	}

	return sql.NullString{String: str, Valid: true}
}

// getIntOptional extracts an optional integer value from a DICOM dataset
func getIntOptional(dataset *dicom.Dataset, tagInfo tag.Tag) sql.NullInt64 {
	elem, err := dataset.FindElementByTag(tagInfo)
	if err != nil || elem == nil {
		return sql.NullInt64{Valid: false}
	}

	value := elem.Value
	if value == nil {
		return sql.NullInt64{Valid: false}
	}

	// Handle int values
	if i, ok := value.GetValue().(int); ok {
		return sql.NullInt64{Int64: int64(i), Valid: true}
	}

	// Handle int64 values
	if i64, ok := value.GetValue().(int64); ok {
		return sql.NullInt64{Int64: i64, Valid: true}
	}

	// Handle uint16 values (common in DICOM)
	if u16, ok := value.GetValue().(uint16); ok {
		return sql.NullInt64{Int64: int64(u16), Valid: true}
	}

	// Handle int slice (take first value)
	if ints, ok := value.GetValue().([]int); ok && len(ints) > 0 {
		return sql.NullInt64{Int64: int64(ints[0]), Valid: true}
	}

	return sql.NullInt64{Valid: false}
}
