package main

import (
	"fmt"
	"os"
	"os/signal"
	"syscall"

	"go.uber.org/zap"
	"screening-gateway/internal/config"
	"screening-gateway/internal/dicom"
	"screening-gateway/internal/relay"
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

	// Create relay sender for MPPS events
	relaySender := relay.NewSender(
		cfg.AzureRelayNamespace,
		cfg.AzureRelayEventsHybridConnection, // Events go TO Django
		cfg.AzureRelayKeyName,
		cfg.AzureRelaySharedAccessKey,
		logger,
	)

	logger.Info("Relay sender initialized",
		zap.String("namespace", cfg.AzureRelayNamespace),
		zap.String("events_connection", cfg.AzureRelayEventsHybridConnection),
	)

	// Create DICOM handlers
	worklistHandler := dicom.NewWorklistHandler(worklistStorage, logger)
	mppsHandler := dicom.NewMPPSHandler(worklistStorage, relaySender, logger)

	// Create DICOM SCP server
	scpServer := dicom.NewWorklistSCP(
		cfg.WorklistAET,
		cfg.WorklistPort,
		worklistHandler,
		mppsHandler,
		logger,
	)

	logger.Info("Starting DICOM Worklist SCP server",
		zap.String("aet", cfg.WorklistAET),
		zap.Int("port", cfg.WorklistPort),
	)

	// Setup graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	// Start SCP server in a goroutine
	serverErr := make(chan error, 1)
	go func() {
		if err := scpServer.Start(); err != nil {
			serverErr <- err
		}
	}()

	// Wait for shutdown signal or server error
	select {
	case <-sigChan:
		logger.Info("Shutdown signal received")
	case err := <-serverErr:
		logger.Fatal("DICOM server error", zap.Error(err))
	}

	logger.Info("Shutting down worklist server")
	if err := scpServer.Stop(); err != nil {
		logger.Error("Error stopping SCP server", zap.Error(err))
	}
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
