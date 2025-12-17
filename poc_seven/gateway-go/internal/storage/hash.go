package storage

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"path/filepath"
)

// ComputeStoragePath computes hash-based storage path for a SOP Instance UID.
//
// Uses first 2 chars of hash as first level, next 2 as second level.
// Example: "1.2.3.4.5" -> hash -> "a1/b2/a1b2c3d4e5f6.dcm"
//
// This MUST match the Python implementation exactly:
// hash_hex = hashlib.sha256(sop_instance_uid.encode()).hexdigest()
// level1 = hash_hex[:2]
// level2 = hash_hex[2:4]
// filename = f"{hash_hex[:16]}.dcm"
// return f"{level1}/{level2}/{filename}"
func ComputeStoragePath(sopInstanceUID string) string {
	// Hash the UID to get consistent path (matches Python hashlib.sha256)
	hash := sha256.Sum256([]byte(sopInstanceUID))
	hashHex := hex.EncodeToString(hash[:])

	// Use first 4 chars for two-level directory structure
	level1 := hashHex[:2]
	level2 := hashHex[2:4]

	// Use first 16 chars of hash as filename
	filename := fmt.Sprintf("%s.dcm", hashHex[:16])

	// Return path in format: "15/77/15770826be837125.dcm"
	return filepath.Join(level1, level2, filename)
}

// ComputeThumbnailPath computes hash-based path for a thumbnail.
// Uses the same hash as DICOM storage but with .jpg extension.
func ComputeThumbnailPath(sopInstanceUID string) string {
	// Hash the UID (same as storage path)
	hash := sha256.Sum256([]byte(sopInstanceUID))
	hashHex := hex.EncodeToString(hash[:])

	// Use first 4 chars for two-level directory structure
	level1 := hashHex[:2]
	level2 := hashHex[2:4]

	// Use first 16 chars of hash as filename with .jpg extension
	filename := fmt.Sprintf("%s.jpg", hashHex[:16])

	// Return path in format: "15/77/15770826be837125.jpg"
	return filepath.Join(level1, level2, filename)
}

// ComputeFileHash computes SHA256 hash of file contents
// Used for integrity verification
func ComputeFileHash(data []byte) string {
	hash := sha256.Sum256(data)
	return hex.EncodeToString(hash[:])
}
