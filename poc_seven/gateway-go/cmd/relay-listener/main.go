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
)

func main() {
	// Initialize logger
	logger := initLogger()
	defer logger.Sync()

	logger.Info("Starting relay listener service")

	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		logger.Fatal("Failed to load configuration", zap.Error(err))
	}

	logger.Info("Configuration loaded",
		zap.String("namespace", cfg.AzureRelayNamespace),
		zap.String("hybrid_connection", cfg.AzureRelayHybridConnection),
		zap.String("worklist_db", cfg.WorklistDBPath),
	)

	// Initialize worklist database
	worklistStorage, err := initWorklistStorage(cfg.WorklistDBPath, logger)
	if err != nil {
		logger.Fatal("Failed to initialize worklist storage", zap.Error(err))
	}
	defer worklistStorage.Close()

	logger.Info("Worklist storage initialized",
		zap.String("database_path", cfg.WorklistDBPath),
	)

	// Create relay listener
	listener := relay.NewListener(
		cfg.AzureRelayNamespace,
		cfg.AzureRelayHybridConnection,
		cfg.AzureRelayKeyName,
		cfg.AzureRelaySharedAccessKey,
		worklistStorage,
		logger,
	)

	// Create context for graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Setup signal handling for graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	// Start listener in goroutine
	errChan := make(chan error, 1)
	go func() {
		logger.Info("Starting Azure Relay listener",
			zap.String("namespace", cfg.AzureRelayNamespace),
			zap.String("hybrid_connection", cfg.AzureRelayHybridConnection),
		)
		if err := listener.Listen(ctx); err != nil && err != context.Canceled {
			errChan <- err
		}
	}()

	// Wait for shutdown signal or error
	select {
	case sig := <-sigChan:
		logger.Info("Received shutdown signal", zap.String("signal", sig.String()))
		cancel()
		// Give listener 10 seconds to shut down gracefully
		time.Sleep(10 * time.Second)
	case err := <-errChan:
		logger.Error("Listener encountered fatal error", zap.Error(err))
		cancel()
		os.Exit(1)
	}

	logger.Info("Relay listener service stopped")
}

// initLogger creates a production-ready zap logger
func initLogger() *zap.Logger {
	// Use production config with console encoding for Docker logs
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

// initWorklistStorage initializes the worklist database with schema
func initWorklistStorage(dbPath string, logger *zap.Logger) (*storage.WorklistStorage, error) {
	// Ensure database directory exists
	dbDir := filepath.Dir(dbPath)
	if err := os.MkdirAll(dbDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create database directory: %w", err)
	}

	// Check if this is first run (database doesn't exist)
	firstRun := false
	if _, err := os.Stat(dbPath); os.IsNotExist(err) {
		firstRun = true
		logger.Info("Database does not exist, will initialize schema",
			zap.String("database_path", dbPath),
		)
	}

	// Initialize schema if first run
	if firstRun {
		logger.Info("Initializing database schema")
		if err := initSchemaDirectly(dbPath); err != nil {
			return nil, fmt.Errorf("failed to initialize schema: %w", err)
		}
		logger.Info("Database schema initialized successfully")
	}

	// Create worklist storage (this will open the database)
	worklistStorage, err := storage.NewWorklistStorage(dbPath)
	if err != nil {
		return nil, fmt.Errorf("failed to create worklist storage: %w", err)
	}

	logger.Info("Worklist database ready",
		zap.String("database_path", dbPath),
		zap.Bool("first_run", firstRun),
	)

	return worklistStorage, nil
}

// initSchemaDirectly initializes the worklist database schema
// Note: In production, this would load from scripts/init_db.sql
// For now, we inline the essential schema
func initSchemaDirectly(dbPath string) error {
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return fmt.Errorf("failed to open database: %w", err)
	}
	defer db.Close()

	schema := `
	CREATE TABLE IF NOT EXISTS worklist_items (
		accession_number TEXT PRIMARY KEY,
		patient_id TEXT NOT NULL,
		patient_name TEXT NOT NULL,
		patient_birth_date TEXT NOT NULL,
		patient_sex TEXT NOT NULL,
		scheduled_date TEXT NOT NULL,
		scheduled_time TEXT NOT NULL,
		modality TEXT NOT NULL,
		study_description TEXT,
		procedure_code TEXT,
		status TEXT NOT NULL DEFAULT 'SCHEDULED',
		study_instance_uid TEXT,
		mpps_instance_uid TEXT,
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		source_message_id TEXT
	);

	CREATE INDEX IF NOT EXISTS idx_worklist_status ON worklist_items(status);
	CREATE INDEX IF NOT EXISTS idx_worklist_scheduled ON worklist_items(scheduled_date, scheduled_time);
	CREATE INDEX IF NOT EXISTS idx_worklist_patient ON worklist_items(patient_id);
	CREATE INDEX IF NOT EXISTS idx_worklist_source ON worklist_items(source_message_id);

	CREATE TRIGGER IF NOT EXISTS update_worklist_timestamp
	AFTER UPDATE ON worklist_items
	BEGIN
		UPDATE worklist_items SET updated_at = CURRENT_TIMESTAMP
		WHERE accession_number = NEW.accession_number;
	END;
	`

	_, err = db.Exec(schema)
	return err
}
