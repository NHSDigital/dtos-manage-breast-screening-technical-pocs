package storage

import (
	"testing"
)

// TestComputeStoragePath verifies that the Go implementation matches Python
func TestComputeStoragePath(t *testing.T) {
	tests := []struct {
		name           string
		sopInstanceUID string
		wantPath       string
	}{
		{
			name:           "example UID 1",
			sopInstanceUID: "1.2.826.0.1.3680043.8.498.97304859",
			// Python: hashlib.sha256(b"1.2.826.0.1.3680043.8.498.97304859").hexdigest()
			// = "e2149e50cbb9f6ed3bb62e534cc8497843b79dc823ea002b98319192933c946d"
			wantPath: "e2/14/e2149e50cbb9f6ed.dcm",
		},
		{
			name:           "example UID 2",
			sopInstanceUID: "1.2.3.4.5.6.7.8.9",
			// Python: hashlib.sha256(b"1.2.3.4.5.6.7.8.9").hexdigest()
			// = "44d0d423f550e42813ccd0e97c057acc5c56ffbf5e63842fa9a2254b73918584"
			wantPath: "44/d0/44d0d423f550e428.dcm",
		},
		{
			name:           "empty UID",
			sopInstanceUID: "",
			// Python: hashlib.sha256(b"").hexdigest()
			// = "e3b0c44298fc1c149afbf4c8996fb924..."
			wantPath: "e3/b0/e3b0c44298fc1c14.dcm",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gotPath := ComputeStoragePath(tt.sopInstanceUID)
			if gotPath != tt.wantPath {
				t.Errorf("ComputeStoragePath(%q) = %q, want %q", tt.sopInstanceUID, gotPath, tt.wantPath)
			}
		})
	}
}

// TestComputeThumbnailPath verifies thumbnail paths match DICOM paths except extension
func TestComputeThumbnailPath(t *testing.T) {
	tests := []struct {
		name           string
		sopInstanceUID string
		wantPath       string
	}{
		{
			name:           "example UID 1",
			sopInstanceUID: "1.2.826.0.1.3680043.8.498.97304859",
			wantPath:       "e2/14/e2149e50cbb9f6ed.jpg",
		},
		{
			name:           "example UID 2",
			sopInstanceUID: "1.2.3.4.5.6.7.8.9",
			wantPath:       "44/d0/44d0d423f550e428.jpg",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gotPath := ComputeThumbnailPath(tt.sopInstanceUID)
			if gotPath != tt.wantPath {
				t.Errorf("ComputeThumbnailPath(%q) = %q, want %q", tt.sopInstanceUID, gotPath, tt.wantPath)
			}
		})
	}
}

// TestComputeFileHash verifies SHA256 hash computation
func TestComputeFileHash(t *testing.T) {
	tests := []struct {
		name     string
		data     []byte
		wantHash string
	}{
		{
			name:     "empty data",
			data:     []byte{},
			wantHash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
		},
		{
			name:     "hello world",
			data:     []byte("hello world"),
			wantHash: "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gotHash := ComputeFileHash(tt.data)
			if gotHash != tt.wantHash {
				t.Errorf("ComputeFileHash(%q) = %q, want %q", string(tt.data), gotHash, tt.wantHash)
			}
		})
	}
}

// BenchmarkComputeStoragePath benchmarks the hash computation
func BenchmarkComputeStoragePath(b *testing.B) {
	uid := "1.2.826.0.1.3680043.8.498.97304859"
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = ComputeStoragePath(uid)
	}
}
