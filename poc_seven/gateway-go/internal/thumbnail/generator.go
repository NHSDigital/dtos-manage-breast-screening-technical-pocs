package thumbnail

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"image"
	_ "image/jpeg" // Register JPEG decoder
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"go.uber.org/zap"
)

// Generator handles thumbnail generation for DICOM images
type Generator struct {
	thumbnailRoot  string
	quality        int
	height         int
	commandTimeout time.Duration
	logger         *zap.Logger
}

// NewGenerator creates a new thumbnail generator
func NewGenerator(thumbnailRoot string, quality, height int, logger *zap.Logger) *Generator {
	return &Generator{
		thumbnailRoot:  thumbnailRoot,
		quality:        quality,
		height:         height,
		commandTimeout: 30 * time.Second,
		logger:         logger,
	}
}

// GenerateThumbnail generates a JPEG thumbnail from a DICOM file using dcm2img
// Returns the path to the generated thumbnail, or an error if generation failed
// Matches Python generate_thumbnail() behavior
func (g *Generator) GenerateThumbnail(dicomPath, sopInstanceUID string) (string, error) {
	// Compute thumbnail path
	thumbnailPath := GetThumbnailPath(g.thumbnailRoot, sopInstanceUID)

	// Ensure thumbnail directory exists
	thumbnailDir := filepath.Dir(thumbnailPath)
	if err := os.MkdirAll(thumbnailDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create thumbnail directory: %w", err)
	}

	// Build dcm2img command
	// +oj: Output JPEG format
	// +Jq <quality>: JPEG quality (1-100)
	// --min-max-window: Use min/max pixel values for windowing
	// --scale-y-size <height>: Scale height to specified size
	cmd := exec.Command(
		"dcm2img",
		"+oj",                          // Output JPEG
		"+Jq", fmt.Sprintf("%d", g.quality), // JPEG quality
		"--min-max-window",             // Min/max windowing
		"--scale-y-size", fmt.Sprintf("%d", g.height), // Scale height
		dicomPath,                      // Input DICOM file
		thumbnailPath,                  // Output JPEG file
	)

	g.logger.Debug("Running dcm2img",
		zap.String("dicom_path", dicomPath),
		zap.String("thumbnail_path", thumbnailPath),
		zap.Int("quality", g.quality),
		zap.Int("height", g.height),
	)

	// Set timeout for command execution
	timer := time.AfterFunc(g.commandTimeout, func() {
		if cmd.Process != nil {
			cmd.Process.Kill()
		}
	})
	defer timer.Stop()

	// Execute dcm2img
	output, err := cmd.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("dcm2img failed: %w (output: %s)", err, string(output))
	}

	// Verify thumbnail was created
	if _, err := os.Stat(thumbnailPath); os.IsNotExist(err) {
		return "", fmt.Errorf("thumbnail not created: %s", thumbnailPath)
	}

	// Get file size for logging
	stat, _ := os.Stat(thumbnailPath)
	g.logger.Info("Generated thumbnail",
		zap.String("thumbnail_path", thumbnailPath),
		zap.Int64("size_bytes", stat.Size()),
	)

	return thumbnailPath, nil
}

// GetThumbnailPath computes the hash-based path for a thumbnail
// Uses the same hash function as DICOM storage (SHA256)
// Returns path like: thumbnails/15/77/15770826be837125.jpg
// Matches Python get_thumbnail_path() behavior
func GetThumbnailPath(thumbnailRoot, sopInstanceUID string) string {
	// Compute SHA256 hash of SOP Instance UID
	hash := sha256.Sum256([]byte(sopInstanceUID))
	hashHex := hex.EncodeToString(hash[:])

	// Two-level directory structure
	level1 := hashHex[:2]
	level2 := hashHex[2:4]
	filename := fmt.Sprintf("%s.jpg", hashHex[:16])

	return filepath.Join(thumbnailRoot, level1, level2, filename)
}

// EncodeThumbnailBase64 reads a thumbnail file and encodes it as base64
// Returns the base64 encoded string, or an error if reading failed
// Matches Python encode_thumbnail_base64() behavior
func EncodeThumbnailBase64(thumbnailPath string) (string, error) {
	// Read thumbnail file
	data, err := os.ReadFile(thumbnailPath)
	if err != nil {
		return "", fmt.Errorf("failed to read thumbnail: %w", err)
	}

	// Encode as base64
	encoded := base64.StdEncoding.EncodeToString(data)
	return encoded, nil
}

// GetThumbnailDimensions reads the dimensions of a JPEG thumbnail
// Returns (width, height) or (0, 0) if unable to read
// Matches Python get_thumbnail_dimensions() behavior
func GetThumbnailDimensions(thumbnailPath string) (int, int, error) {
	// Open thumbnail file
	file, err := os.Open(thumbnailPath)
	if err != nil {
		return 0, 0, fmt.Errorf("failed to open thumbnail: %w", err)
	}
	defer file.Close()

	// Decode image to get dimensions (without loading full image data)
	config, _, err := image.DecodeConfig(file)
	if err != nil {
		return 0, 0, fmt.Errorf("failed to decode image config: %w", err)
	}

	return config.Width, config.Height, nil
}
