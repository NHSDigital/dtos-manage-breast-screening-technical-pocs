package main

import (
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"go.uber.org/zap"
	"screening-gateway/internal/config"
	"screening-gateway/internal/dicom"
	"screening-gateway/internal/storage"
)

func main() {
	// Load configuration
	cfg := config.MustLoad()

	// Setup structured logging
	logger, err := zap.NewProduction()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to create logger: %v\n", err)
		os.Exit(1)
	}
	defer logger.Sync()

	logger.Info("Starting DICOM Modality Worklist Server with MPPS Support",
		zap.String("aet", cfg.WorklistAET),
		zap.Int("port", cfg.WorklistPort),
		zap.String("db_path", cfg.WorklistDBPath),
	)

	// Initialize worklist storage
	worklistStorage, err := storage.NewWorklistStorage(cfg.WorklistDBPath)
	if err != nil {
		logger.Fatal("Failed to initialize worklist storage", zap.Error(err))
	}
	defer worklistStorage.Close()

	// Get storage statistics
	stats, err := worklistStorage.GetStatistics()
	if err != nil {
		logger.Warn("Failed to get storage statistics", zap.Error(err))
	} else {
		logger.Info("Worklist storage initialized",
			zap.Any("stats", stats),
		)
	}

	// Create DICOM handlers
	worklistHandler := dicom.NewWorklistHandler(worklistStorage, logger)
	mppsHandler := dicom.NewMPPSHandler(worklistStorage, logger)

	// TODO: Integrate with DICOM networking library
	// The following needs to be implemented with a DICOM SCP library:
	//
	// 1. Create DICOM Application Entity (AE) with AET from config
	// 2. Add supported contexts:
	//    - C-ECHO (Verification SOP Class)
	//    - C-FIND (Modality Worklist Information Model - FIND)
	//    - N-CREATE (Modality Performed Procedure Step - CREATE)
	//    - N-SET (Modality Performed Procedure Step - SET)
	// 3. Register event handlers:
	//    - C-ECHO: Return success (0x0000)
	//    - C-FIND: Call worklistHandler.FindWorklist() and yield results
	//    - N-CREATE: Call mppsHandler.HandleNCreate()
	//    - N-SET: Call mppsHandler.HandleNSet()
	// 4. Start DICOM server on configured port
	// 5. Handle graceful shutdown
	//
	// Example pseudocode:
	//
	// ae := dicomnet.NewApplicationEntity(cfg.WorklistAET)
	// ae.AddSupportedContext(dicomnet.VerificationSOPClass)
	// ae.AddSupportedContext(dicomnet.ModalityWorklistInformationFind)
	// ae.AddSupportedContext(dicomnet.ModalityPerformedProcedureStep)
	//
	// ae.OnCEcho(func(assoc *Association) uint16 {
	//     logger.Info("Received C-ECHO request")
	//     return 0x0000 // Success
	// })
	//
	// ae.OnCFind(func(assoc *Association, query *Dataset) Iterator {
	//     // Extract query parameters from DICOM dataset
	//     modality := extractModality(query)
	//     scheduledDate := extractScheduledDate(query)
	//
	//     // Query worklist
	//     results, err := worklistHandler.FindWorklist(&dicom.WorklistQuery{
	//         Modality:      modality,
	//         ScheduledDate: scheduledDate,
	//     })
	//
	//     // Convert results to DICOM datasets and yield
	//     return newWorklistIterator(results)
	// })
	//
	// ae.OnNCreate(func(assoc *Association, req *NCreateRequest) (uint16, *Dataset) {
	//     // Extract from request
	//     sopInstanceUID := req.AffectedSOPInstanceUID
	//     attrList := req.AttributeList
	//
	//     // Validate status is "IN PROGRESS"
	//     status := attrList.Get("PerformedProcedureStepStatus")
	//     if status != "IN PROGRESS" {
	//         return 0x0106, nil // Invalid attribute value
	//     }
	//
	//     // Extract scheduled step attributes
	//     accessionNumber, studyUID, modality := extractScheduledStepAttributes(attrList)
	//
	//     // Call handler
	//     success, err := mppsHandler.HandleNCreate(sopInstanceUID, status, accessionNumber, studyUID, modality)
	//     if !success || err != nil {
	//         return 0x0110, nil // Processing failure
	//     }
	//
	//     // Build response dataset
	//     responseDS := buildMPPSResponse(sopInstanceUID, attrList)
	//     return 0x0000, responseDS // Success
	// })
	//
	// ae.OnNSet(func(assoc *Association, req *NSetRequest) (uint16, *Dataset) {
	//     sopInstanceUID := req.RequestedSOPInstanceUID
	//     modList := req.ModificationList
	//     status := modList.Get("PerformedProcedureStepStatus")
	//
	//     success, err := mppsHandler.HandleNSet(sopInstanceUID, status)
	//     if !success || err != nil {
	//         if err.Error() == "SOP Instance UID not recognized" {
	//             return 0x0112, nil // SOP Instance not recognized
	//         }
	//         return 0x0110, nil // Processing failure
	//     }
	//
	//     // Get managed instance and build response
	//     instance, _ := mppsHandler.GetManagedInstance(sopInstanceUID)
	//     responseDS := buildMPPSResponse(sopInstanceUID, modList)
	//     return 0x0000, responseDS // Success
	// })
	//
	// server, err := ae.Listen(cfg.WorklistPort)
	// if err != nil {
	//     logger.Fatal("Failed to start DICOM server", zap.Error(err))
	// }
	// defer server.Close()

	logger.Info("Worklist server would start here - DICOM networking library integration needed")
	logger.Info("Handlers ready to process requests",
		zap.String("worklist_handler", fmt.Sprintf("%T", worklistHandler)),
		zap.String("mpps_handler", fmt.Sprintf("%T", mppsHandler)),
	)

	// Setup graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	logger.Info("Worklist server initialized (waiting for DICOM networking integration)")
	<-sigChan

	logger.Info("Shutting down worklist server")
}

/*
DICOM Networking Library Requirements:

To complete this server, we need a Go library that provides:

1. **DICOM Service Class Provider (SCP)** functionality
2. Support for C-ECHO (Verification)
3. Support for C-FIND (Modality Worklist)
4. Support for N-CREATE and N-SET (MPPS)
5. Ability to extract and build DICOM datasets

The business logic is fully implemented in:
- internal/dicom/worklist.go (WorklistHandler)
- internal/dicom/mpps.go (MPPSHandler)
- internal/storage/worklist.go (WorklistStorage)

Key DICOM tags that need to be extracted:
- Modality Worklist query:
  - (0040,0100) ScheduledProcedureStepSequence
    - (0008,0060) Modality
    - (0040,0002) ScheduledProcedureStepStartDate
  - (0010,0020) PatientID (optional)

- MPPS N-CREATE:
  - AffectedSOPInstanceUID
  - (0040,0252) PerformedProcedureStepStatus (must be "IN PROGRESS")
  - (0040,0270) ScheduledStepAttributesSequence
    - (0008,0050) AccessionNumber
    - (0020,000D) StudyInstanceUID
  - (0008,0060) Modality

- MPPS N-SET:
  - RequestedSOPInstanceUID
  - (0040,0252) PerformedProcedureStepStatus (COMPLETED or DISCONTINUED)

All that's needed is the networking layer to route requests to the handlers.
*/
