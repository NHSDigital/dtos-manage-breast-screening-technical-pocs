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

	logger.Info("Starting DICOM PACS Server",
		zap.String("aet", cfg.PACSAET),
		zap.Int("port", cfg.PACSPort),
		zap.String("storage_path", cfg.PACSStoragePath),
		zap.String("db_path", cfg.PACSDBPath),
	)

	// Initialize PACS storage
	pacsStorage, err := storage.NewPACSStorage(cfg.PACSDBPath, cfg.PACSStoragePath)
	if err != nil {
		logger.Fatal("Failed to initialize PACS storage", zap.Error(err))
	}
	defer pacsStorage.Close()

	// Get storage statistics
	stats, err := pacsStorage.GetStatistics()
	if err != nil {
		logger.Warn("Failed to get storage statistics", zap.Error(err))
	} else {
		logger.Info("PACS storage initialized",
			zap.Any("stats", stats),
		)
	}

	// Create DICOM handlers
	storeHandler := dicom.NewStoreHandler(pacsStorage, logger)

	// TODO: Integrate with DICOM networking library
	// The following needs to be implemented with a DICOM SCP library:
	//
	// 1. Create DICOM Application Entity (AE) with AET from config
	// 2. Add supported contexts:
	//    - C-ECHO (Verification SOP Class)
	//    - C-STORE (All 120+ Storage SOP Classes for mammography)
	// 3. Register event handlers:
	//    - C-ECHO: Return success (0x0000)
	//    - C-STORE: Call storeHandler.HandleStore() for each received image
	// 4. Start DICOM server on configured port
	// 5. Handle graceful shutdown
	//
	// Example pseudocode:
	//
	// ae := dicomnet.NewApplicationEntity(cfg.PACSAET)
	// ae.AddSupportedContext(dicomnet.VerificationSOPClass)
	// ae.AddAllStorageContexts() // All 120+ storage SOP classes
	//
	// ae.OnCEcho(func(assoc *Association) uint16 {
	//     logger.Info("Received C-ECHO request")
	//     return 0x0000 // Success
	// })
	//
	// ae.OnCStore(func(assoc *Association, dataset []byte) uint16 {
	//     sourceAET := assoc.CallingAET()
	//     success, err := storeHandler.HandleStore(dataset, sourceAET)
	//     if err != nil {
	//         logger.Error("C-STORE failed", zap.Error(err))
	//         return 0xC000 // Failure
	//     }
	//     if success {
	//         return 0x0000 // Success
	//     }
	//     return 0xC000 // Failure
	// })
	//
	// server, err := ae.Listen(cfg.PACSPort)
	// if err != nil {
	//     logger.Fatal("Failed to start DICOM server", zap.Error(err))
	// }
	// defer server.Close()

	logger.Info("PACS server would start here - DICOM networking library integration needed")
	logger.Info("StoreHandler ready to process C-STORE requests",
		zap.String("handler", fmt.Sprintf("%T", storeHandler)),
	)

	// Setup graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	logger.Info("PACS server initialized (waiting for DICOM networking integration)")
	<-sigChan

	logger.Info("Shutting down PACS server")
}

/*
DICOM Networking Library Requirements:

To complete this server, we need a Go library that provides:

1. **DICOM Service Class Provider (SCP)** functionality
2. Support for C-ECHO (Verification)
3. Support for C-STORE with multiple SOP classes
4. Ability to extract:
   - Calling AE Title
   - DICOM datasets as bytes
   - File meta information

Potential libraries to evaluate:
- github.com/suyashkumar/go-netdicom (if it exists and supports SCP)
- Custom implementation using lower-level DICOM networking
- CGO wrapper around DCMTK (dcmnet library)

The business logic for C-STORE is fully implemented in:
- internal/dicom/store.go (StoreHandler)
- internal/dicom/metadata.go (ExtractMetadata)
- internal/storage/pacs.go (PACSStorage)

All that's needed is the networking layer to receive DICOM associations
and route C-STORE requests to StoreHandler.HandleStore().
*/
