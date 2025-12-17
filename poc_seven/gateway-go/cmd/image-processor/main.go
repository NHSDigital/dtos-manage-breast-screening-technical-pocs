package main

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"

	"screening-gateway/internal/config"
	"screening-gateway/internal/relay"
	"screening-gateway/internal/storage"
	"screening-gateway/internal/thumbnail"
)

func main() {
	// Initialize logger
	logger := initLogger()
	defer logger.Sync()

	logger.Info("=" + "========================================================")
	logger.Info("Starting Image Processor Service")
	logger.Info("=" + "========================================================")

	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		logger.Fatal("Failed to load configuration", zap.Error(err))
	}

	logger.Info("Configuration loaded",
		zap.String("pacs_db", cfg.PACSDBPath),
		zap.String("worklist_db", cfg.WorklistDBPath),
		zap.String("storage_root", cfg.PACSStorageRoot),
		zap.String("thumbnail_root", cfg.ThumbnailRoot),
		zap.Int("poll_interval", cfg.ImagePollInterval),
		zap.Int("batch_size", cfg.ImageBatchSize),
		zap.Int("thumbnail_quality", cfg.ThumbnailQuality),
		zap.Int("thumbnail_height", cfg.ThumbnailHeight),
	)

	// Initialize PACS storage
	pacsStorage, err := storage.NewPACSStorage(cfg.PACSDBPath, cfg.PACSStorageRoot)
	if err != nil {
		logger.Fatal("Failed to initialize PACS storage", zap.Error(err))
	}
	defer pacsStorage.Close()

	// Initialize worklist storage (for action_id lookup)
	worklistStorage, err := storage.NewWorklistStorage(cfg.WorklistDBPath)
	if err != nil {
		logger.Fatal("Failed to initialize worklist storage", zap.Error(err))
	}
	defer worklistStorage.Close()

	// Create thumbnail generator
	thumbnailGen := thumbnail.NewGenerator(
		cfg.ThumbnailRoot,
		cfg.ThumbnailQuality,
		cfg.ThumbnailHeight,
		logger,
	)

	// Ensure thumbnail root exists
	if err := os.MkdirAll(cfg.ThumbnailRoot, 0755); err != nil {
		logger.Fatal("Failed to create thumbnail directory", zap.Error(err))
	}

	// Create relay sender for image events
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

	// Create image processor
	processor := &ImageProcessor{
		pacsStorage:     pacsStorage,
		worklistStorage: worklistStorage,
		thumbnailGen:    thumbnailGen,
		relaySender:     relaySender,
		storageRoot:     cfg.PACSStorageRoot,
		pollInterval:    time.Duration(cfg.ImagePollInterval) * time.Second,
		batchSize:       cfg.ImageBatchSize,
		logger:          logger,
	}

	logger.Info("=" + "========================================================")

	// Create context for graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Setup signal handling
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	// Start processor in goroutine
	go func() {
		if err := processor.Run(ctx); err != nil && err != context.Canceled {
			logger.Error("Processor error", zap.Error(err))
		}
	}()

	// Wait for shutdown signal
	sig := <-sigChan
	logger.Info("Received shutdown signal", zap.String("signal", sig.String()))
	cancel()

	// Give processor time to finish current batch
	time.Sleep(2 * time.Second)

	logger.Info("Image processor service stopped")
}

// ImageProcessor processes pending DICOM images
type ImageProcessor struct {
	pacsStorage     *storage.PACSStorage
	worklistStorage *storage.WorklistStorage
	thumbnailGen    *thumbnail.Generator
	relaySender     *relay.Sender
	storageRoot     string
	pollInterval    time.Duration
	batchSize       int
	logger          *zap.Logger
}

// Run starts the image processing loop
func (p *ImageProcessor) Run(ctx context.Context) error {
	ticker := time.NewTicker(p.pollInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			p.logger.Info("Processor shutdown requested")
			return ctx.Err()
		case <-ticker.C:
			if err := p.processPendingImages(ctx); err != nil {
				p.logger.Error("Error processing images", zap.Error(err))
			}
		}
	}
}

// processPendingImages processes a batch of pending images
func (p *ImageProcessor) processPendingImages(ctx context.Context) error {
	// Get pending images from database
	pending, err := p.pacsStorage.GetPendingThumbnails(p.batchSize)
	if err != nil {
		return fmt.Errorf("failed to get pending images: %w", err)
	}

	if len(pending) == 0 {
		return nil
	}

	p.logger.Info("Found images pending processing", zap.Int("count", len(pending)))

	for _, instance := range pending {
		// Check if shutdown requested
		select {
		case <-ctx.Done():
			p.logger.Info("Shutdown requested, stopping image processing")
			return ctx.Err()
		default:
		}

		if err := p.processImage(ctx, instance); err != nil {
			p.logger.Error("Failed to process image",
				zap.String("sop_instance_uid", instance.SOPInstanceUID),
				zap.Error(err),
			)
			// Mark as failed
			errMsg := err.Error()
			p.pacsStorage.UpdateThumbnailStatus(
				instance.SOPInstanceUID,
				storage.ThumbnailStatusFailed,
				&errMsg,
			)
		}
	}

	return nil
}

// processImage processes a single DICOM image
func (p *ImageProcessor) processImage(ctx context.Context, instance *storage.StoredInstance) error {
	p.logger.Info("Processing image", zap.String("sop_instance_uid", instance.SOPInstanceUID))

	// Construct full DICOM file path
	dicomPath := filepath.Join(p.storageRoot, instance.StoragePath)

	// Check if DICOM file exists
	if _, err := os.Stat(dicomPath); os.IsNotExist(err) {
		return fmt.Errorf("DICOM file not found: %s", dicomPath)
	}

	// Generate thumbnail
	thumbnailPath, err := p.thumbnailGen.GenerateThumbnail(dicomPath, instance.SOPInstanceUID)
	if err != nil {
		return fmt.Errorf("thumbnail generation failed: %w", err)
	}

	// Encode thumbnail to base64
	thumbnailB64, err := thumbnail.EncodeThumbnailBase64(thumbnailPath)
	if err != nil {
		return fmt.Errorf("thumbnail encoding failed: %w", err)
	}

	// Get thumbnail dimensions
	width, height, err := thumbnail.GetThumbnailDimensions(thumbnailPath)
	if err != nil {
		p.logger.Warn("Failed to get thumbnail dimensions", zap.Error(err))
		width, height = 0, 0
	}

	p.logger.Info("Generated thumbnail",
		zap.String("path", thumbnailPath),
		zap.Int("width", width),
		zap.Int("height", height),
	)

	// Look up action_id from worklist database
	var actionID *string
	if instance.AccessionNumber.Valid && instance.AccessionNumber.String != "" {
		actionID, err = p.lookupActionID(instance.AccessionNumber.String)
		if err != nil {
			p.logger.Warn("Failed to lookup action_id",
				zap.String("accession_number", instance.AccessionNumber.String),
				zap.Error(err),
			)
		}
	}

	// Build image_received message
	message := buildImageReceivedMessage(instance, thumbnailB64, width, height, actionID)

	// Send message via relay
	if err := p.relaySender.SendImageEventSync(message); err != nil {
		return fmt.Errorf("failed to send image message: %w", err)
	}

	p.logger.Info("Image message sent successfully",
		zap.String("sop_instance_uid", instance.SOPInstanceUID),
	)

	// Mark as successfully processed
	if err := p.pacsStorage.UpdateThumbnailStatus(
		instance.SOPInstanceUID,
		storage.ThumbnailStatusGenerated,
		nil, // No error
	); err != nil {
		return fmt.Errorf("failed to update thumbnail status: %w", err)
	}

	p.logger.Info("Successfully processed image", zap.String("sop_instance_uid", instance.SOPInstanceUID))

	return nil
}

// lookupActionID looks up the action_id from worklist database by accession number
func (p *ImageProcessor) lookupActionID(accessionNumber string) (*string, error) {
	query := `
		SELECT source_message_id
		FROM worklist_items
		WHERE accession_number = ?
	`

	db := p.worklistStorage.DB()
	var sourceMessageID sql.NullString
	err := db.QueryRow(query, accessionNumber).Scan(&sourceMessageID)
	if err == sql.ErrNoRows {
		p.logger.Debug("No action_id found for accession number",
			zap.String("accession_number", accessionNumber),
		)
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("database query failed: %w", err)
	}

	if !sourceMessageID.Valid {
		return nil, nil
	}

	actionID := sourceMessageID.String
	p.logger.Debug("Found action_id for accession number",
		zap.String("accession_number", accessionNumber),
		zap.String("action_id", actionID),
	)

	return &actionID, nil
}

// buildImageReceivedMessage builds the image_received message matching Python schema
func buildImageReceivedMessage(
	instance *storage.StoredInstance,
	thumbnailB64 string,
	width, height int,
	actionID *string,
) *relay.ImageReceivedMessage {
	// Helper to convert sql.NullString to *string
	nullStringToPtr := func(ns sql.NullString) *string {
		if ns.Valid {
			return &ns.String
		}
		return nil
	}

	// Helper to convert sql.NullInt64 to *int64
	nullInt64ToPtr := func(ni sql.NullInt64) *int64 {
		if ni.Valid {
			return &ni.Int64
		}
		return nil
	}

	receivedAt := instance.ReceivedAt.Format(time.RFC3339)
	modality := instance.Modality

	message := &relay.ImageReceivedMessage{
		SchemaVersion: 1,
		MessageType:   "study.image_received",
		Timestamp:     time.Now().UTC().Format(time.RFC3339),
		SourceSystem:  "gateway-pacs",
		SourceReference: relay.SourceReference{
			ActionID: actionID,
		},
		Parameters: relay.ImageMessageParameters{
			Participant: relay.ParticipantInfo{
				NHSNumber:   nullStringToPtr(instance.PatientID),
				PatientName: nullStringToPtr(instance.PatientName),
			},
			Study: relay.StudyInfo{
				AccessionNumber:  nullStringToPtr(instance.AccessionNumber),
				StudyInstanceUID: instance.StudyInstanceUID,
				Modality:         &modality,
				StudyDate:        nullStringToPtr(instance.StudyDate),
				StudyTime:        nullStringToPtr(instance.StudyTime),
				StudyDescription: nullStringToPtr(instance.StudyDescription),
			},
			Series: relay.SeriesInfo{
				SeriesInstanceUID: instance.SeriesInstanceUID,
				SeriesNumber:      nullStringToPtr(instance.SeriesNumber),
				SeriesDescription: nullStringToPtr(instance.SeriesDescription),
			},
			Image: relay.ImageInfo{
				SOPInstanceUID: instance.SOPInstanceUID,
				InstanceNumber: nullStringToPtr(instance.InstanceNumber),
				Dimensions: &relay.ImageDimensions{
					Rows:    nullInt64ToPtr(instance.Rows),
					Columns: nullInt64ToPtr(instance.Columns),
				},
				Acquisition: &relay.ImageAcquisition{
					ViewPosition: nullStringToPtr(instance.ViewPosition),
					Laterality:   nullStringToPtr(instance.Laterality),
				},
				Dose: &relay.DoseInformation{
					OrganDose:           nullStringToPtr(instance.OrganDose),
					EntranceDoseInMgy:   nullStringToPtr(instance.EntranceDoseInMgy),
					KVP:                 nullStringToPtr(instance.KVP),
					ExposureInUas:       nullStringToPtr(instance.ExposureInUas),
					AnodeTargetMaterial: nullStringToPtr(instance.AnodeTargetMaterial),
					FilterMaterial:      nullStringToPtr(instance.FilterMaterial),
					FilterThickness:     nullStringToPtr(instance.FilterThickness),
				},
				ReceivedAt: &receivedAt,
			},
		},
	}

	// Add thumbnail if available
	if thumbnailB64 != "" {
		message.Parameters.Image.Thumbnail = &relay.ThumbnailInfo{
			Data:   thumbnailB64,
			Format: "jpeg",
			Width:  width,
			Height: height,
		}
	}

	return message
}

// initLogger creates a production-ready zap logger
func initLogger() *zap.Logger {
	config := zap.NewProductionConfig()
	config.Encoding = "console"
	config.EncoderConfig.TimeKey = "timestamp"
	config.EncoderConfig.EncodeTime = zapcore.ISO8601TimeEncoder
	config.EncoderConfig.EncodeLevel = zapcore.CapitalLevelEncoder

	logger, err := config.Build()
	if err != nil {
		panic(fmt.Sprintf("Failed to initialize logger: %v", err))
	}

	return logger
}
