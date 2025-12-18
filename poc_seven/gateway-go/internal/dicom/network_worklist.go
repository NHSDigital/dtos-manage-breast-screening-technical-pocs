package dicom

import (
	"github.com/t2care/obd-dicom/dictionary/tags"
	"github.com/t2care/obd-dicom/media"
	"github.com/t2care/obd-dicom/network"
	"github.com/t2care/obd-dicom/network/dicomstatus"
	"go.uber.org/zap"
)

// WorklistSCP is a DICOM SCP server for Modality Worklist
type WorklistSCP struct {
	aet             string
	port            int
	scp             interface{} // Will be *network.scp but it's unexported
	worklistHandler *WorklistHandler
	mppsHandler     *MPPSHandler
	logger          *zap.Logger
}

// NewWorklistSCP creates a new worklist SCP server
func NewWorklistSCP(aet string, port int, worklistHandler *WorklistHandler, mppsHandler *MPPSHandler, logger *zap.Logger) *WorklistSCP {
	return &WorklistSCP{
		aet:             aet,
		port:            port,
		worklistHandler: worklistHandler,
		mppsHandler:     mppsHandler,
		logger:          logger,
	}
}

// Start initializes and starts the DICOM SCP server
func (s *WorklistSCP) Start() error {
	s.logger.Info("Starting DICOM Worklist SCP server",
		zap.String("aet", s.aet),
		zap.Int("port", s.port),
	)

	// Create SCP server
	s.scp = network.NewSCP(s.port)

	// Setup association request handler
	s.scp.OnAssociationRequest(func(request *network.AAssociationRQ) bool {
		calledAET := request.GetCalledAE()
		callingAET := request.GetCallingAE()

		s.logger.Info("Association request",
			zap.String("called_aet", calledAET),
			zap.String("calling_aet", callingAET),
		)

		// Accept if called AET matches our AET
		accepted := calledAET == s.aet
		if !accepted {
			s.logger.Warn("Rejected association - AET mismatch",
				zap.String("expected", s.aet),
				zap.String("received", calledAET),
			)
		}

		return accepted
	})

	// Setup association release handler
	s.scp.OnAssociationRelease(func(request *network.AAssociationRQ) {
		s.logger.Info("Association released",
			zap.String("calling_aet", request.GetCallingAE()),
		)
	})

	// Setup C-FIND handler for worklist queries
	s.scp.OnCFindRequest(func(request *network.AAssociationRQ, query *media.DcmObj) ([]*media.DcmObj, uint16) {
		return s.handleCFind(request, query)
	})

	// TODO: Setup N-CREATE and N-SET handlers for MPPS
	// The obd-dicom library may not support N-CREATE/N-SET directly
	// We may need to check if it supports these operations or use grailbio/go-netdicom for MPPS

	// Start the SCP server
	s.logger.Info("DICOM SCP server listening",
		zap.String("aet", s.aet),
		zap.Int("port", s.port),
	)

	// Start() blocks until server stops
	return s.scp.Start()
}

// Stop gracefully stops the SCP server
func (s *WorklistSCP) Stop() error {
	if s.scp != nil {
		s.logger.Info("Stopping DICOM SCP server")
		// Note: obd-dicom may not have a Stop() method
		// The server stops when Start() returns
	}
	return nil
}

// handleCFind processes C-FIND requests for modality worklist queries
func (s *WorklistSCP) handleCFind(request *network.AAssociationRQ, query *media.DcmObj) ([]*media.DcmObj, uint16) {
	s.logger.Info("Received C-FIND request",
		zap.String("calling_aet", request.GetCallingAE()),
	)

	// Extract query parameters from DICOM object
	worklistQuery := s.extractWorklistQuery(query)

	// Call worklist handler
	results, err := s.worklistHandler.FindWorklist(worklistQuery)
	if err != nil {
		s.logger.Error("Worklist query failed", zap.Error(err))
		return nil, dicomstatus.FailureUnableToProcess
	}

	// Convert results to DICOM objects
	dicomResults := make([]*media.DcmObj, 0, len(results))
	for _, result := range results {
		dcmObj, err := s.convertWorklistResponseToDicom(result)
		if err != nil {
			s.logger.Error("Failed to convert worklist response", zap.Error(err))
			continue
		}
		dicomResults = append(dicomResults, dcmObj)
	}

	s.logger.Info("C-FIND completed",
		zap.Int("result_count", len(dicomResults)),
	)

	return dicomResults, dicomstatus.Success
}

// extractWorklistQuery extracts query parameters from DICOM C-FIND request
func (s *WorklistSCP) extractWorklistQuery(query *media.DcmObj) *WorklistQuery {
	worklistQuery := &WorklistQuery{}

	// Extract Modality (0008,0060) - may be at root level or in SPS sequence
	if modality := query.GetString(tags.Modality); modality != "" {
		worklistQuery.Modality = &modality
	}

	// Extract ScheduledProcedureStepStartDate (0040,0002)
	if scheduledDate := query.GetString(tags.ScheduledProcedureStepStartDate); scheduledDate != "" {
		worklistQuery.ScheduledDate = &scheduledDate
	}

	// Extract PatientID (0010,0020)
	if patientID := query.GetString(tags.PatientID); patientID != "" {
		worklistQuery.PatientID = &patientID
	}

	s.logger.Info("Extracted worklist query",
		zap.Stringp("modality", worklistQuery.Modality),
		zap.Stringp("scheduled_date", worklistQuery.ScheduledDate),
		zap.Stringp("patient_id", worklistQuery.PatientID),
	)

	return worklistQuery
}

// convertWorklistResponseToDicom converts a WorklistResponse to a DICOM object
func (s *WorklistSCP) convertWorklistResponseToDicom(response *WorklistResponse) (*media.DcmObj, error) {
	// Create a new DICOM object by reading from a file or creating empty
	// For now, we'll need to use media.ReadDicomObjFromFile or similar
	// But for worklist responses, we need to build the response programmatically

	// TODO: This requires understanding how to create a new DcmObj from scratch
	// The obd-dicom library may not have a NewDcmObj() method
	// We may need to load a template or use a different approach

	// For now, create an empty object (this will need proper implementation)
	dcmObj := &media.DcmObj{}

	// Note: We need to properly add tags to the DICOM object
	// The obd-dicom API doesn't seem to have a simple SetString() method
	// We may need to create DcmTag objects and add them

	s.logger.Warn("DICOM object creation not fully implemented - returning empty object")

	return dcmObj, nil
}
