package config

import (
	"fmt"
	"os"

	"github.com/kelseyhightower/envconfig"
)

// Config holds all configuration for the gateway services
type Config struct {
	// Azure Relay Configuration
	AzureRelayNamespace             string `envconfig:"AZURE_RELAY_NAMESPACE" required:"true"`
	AzureRelayHybridConnection      string `envconfig:"AZURE_RELAY_HYBRID_CONNECTION" required:"true"`
	AzureRelayEventsHybridConnection string `envconfig:"AZURE_RELAY_EVENTS_HYBRID_CONNECTION" required:"true"`
	AzureRelayKeyName               string `envconfig:"AZURE_RELAY_KEY_NAME" required:"true"`
	AzureRelaySharedAccessKey       string `envconfig:"AZURE_RELAY_SHARED_ACCESS_KEY" required:"true"`

	// Worklist Server Configuration
	WorklistAET    string `envconfig:"WORKLIST_AET" default:"SCREENING_MWL"`
	WorklistPort   int    `envconfig:"WORKLIST_PORT" default:"4243"`
	WorklistDBPath string `envconfig:"WORKLIST_DB_PATH" default:"/var/lib/worklist/worklist.db"`

	// PACS Server Configuration
	PACSAET        string `envconfig:"PACS_AET" default:"SCREENING_PACS"`
	PACSPort       int    `envconfig:"PACS_PORT" default:"4244"`
	PACSStoragePath string `envconfig:"PACS_STORAGE_PATH" default:"/var/lib/pacs/storage"`
	PACSDBPath     string `envconfig:"PACS_DB_PATH" default:"/var/lib/pacs/pacs.db"`

	// Image Processor Configuration
	PACSStorageRoot  string `envconfig:"PACS_STORAGE_ROOT" default:"/var/lib/pacs/storage"`
	ThumbnailRoot    string `envconfig:"THUMBNAIL_ROOT" default:"/var/lib/pacs/thumbnails"`
	ImagePollInterval int    `envconfig:"IMAGE_POLL_INTERVAL" default:"2"` // seconds
	ImageBatchSize   int    `envconfig:"IMAGE_BATCH_SIZE" default:"10"`
	ThumbnailQuality int    `envconfig:"THUMBNAIL_QUALITY" default:"25"`
	ThumbnailHeight  int    `envconfig:"THUMBNAIL_HEIGHT" default:"188"`

	// General Configuration
	LogLevel string `envconfig:"LOG_LEVEL" default:"INFO"`
}

// Load reads configuration from environment variables
func Load() (*Config, error) {
	var cfg Config
	if err := envconfig.Process("", &cfg); err != nil {
		return nil, fmt.Errorf("failed to load configuration: %w", err)
	}
	return &cfg, nil
}

// Validate checks if the configuration is valid
func (c *Config) Validate() error {
	// Check Azure Relay configuration
	if c.AzureRelayNamespace == "" {
		return fmt.Errorf("AZURE_RELAY_NAMESPACE is required")
	}
	if c.AzureRelayHybridConnection == "" {
		return fmt.Errorf("AZURE_RELAY_HYBRID_CONNECTION is required")
	}
	if c.AzureRelayEventsHybridConnection == "" {
		return fmt.Errorf("AZURE_RELAY_EVENTS_HYBRID_CONNECTION is required")
	}
	if c.AzureRelayKeyName == "" {
		return fmt.Errorf("AZURE_RELAY_KEY_NAME is required")
	}
	if c.AzureRelaySharedAccessKey == "" {
		return fmt.Errorf("AZURE_RELAY_SHARED_ACCESS_KEY is required")
	}

	// Check DICOM ports
	if c.WorklistPort < 1 || c.WorklistPort > 65535 {
		return fmt.Errorf("WORKLIST_PORT must be between 1 and 65535")
	}
	if c.PACSPort < 1 || c.PACSPort > 65535 {
		return fmt.Errorf("PACS_PORT must be between 1 and 65535")
	}

	// Check image processor configuration
	if c.ImagePollInterval < 1 {
		return fmt.Errorf("IMAGE_POLL_INTERVAL must be at least 1 second")
	}
	if c.ImageBatchSize < 1 {
		return fmt.Errorf("IMAGE_BATCH_SIZE must be at least 1")
	}
	if c.ThumbnailQuality < 1 || c.ThumbnailQuality > 100 {
		return fmt.Errorf("THUMBNAIL_QUALITY must be between 1 and 100")
	}
	if c.ThumbnailHeight < 1 {
		return fmt.Errorf("THUMBNAIL_HEIGHT must be positive")
	}

	return nil
}

// MustLoad loads configuration and panics on error
// Use this in main() functions where you want to fail fast
func MustLoad() *Config {
	cfg, err := Load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to load configuration: %v\n", err)
		os.Exit(1)
	}
	if err := cfg.Validate(); err != nil {
		fmt.Fprintf(os.Stderr, "Invalid configuration: %v\n", err)
		os.Exit(1)
	}
	return cfg
}
