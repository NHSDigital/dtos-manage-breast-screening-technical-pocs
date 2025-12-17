package relay

import (
	"strings"
	"testing"
)

// TestCreateSASToken verifies SAS token generation matches Python implementation
func TestCreateSASToken(t *testing.T) {
	tests := []struct {
		name           string
		namespace      string
		entityPath     string
		keyName        string
		key            string
		expirySeconds  int
		wantPrefix     string
		wantContains   []string
	}{
		{
			name:          "basic token generation",
			namespace:     "test-namespace.servicebus.windows.net",
			entityPath:    "test-hc",
			keyName:       "RootManageSharedAccessKey",
			key:           "testkey123",
			expirySeconds: 3600,
			wantPrefix:    "SharedAccessSignature ",
			wantContains: []string{
				"sr=http",
				"sig=",
				"se=",
				"skn=RootManageSharedAccessKey",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			token, err := CreateSASToken(
				tt.namespace,
				tt.entityPath,
				tt.keyName,
				tt.key,
				tt.expirySeconds,
			)

			if err != nil {
				t.Errorf("CreateSASToken() error = %v", err)
				return
			}

			// Check prefix
			if !strings.HasPrefix(token, tt.wantPrefix) {
				t.Errorf("Token does not start with %q, got: %s", tt.wantPrefix, token)
			}

			// Check required components
			for _, want := range tt.wantContains {
				if !strings.Contains(token, want) {
					t.Errorf("Token missing required component %q, got: %s", want, token)
				}
			}

			// Verify token structure
			if !strings.Contains(token, "sr=") {
				t.Error("Token missing sr (SignedResource) parameter")
			}
			if !strings.Contains(token, "sig=") {
				t.Error("Token missing sig (Signature) parameter")
			}
			if !strings.Contains(token, "se=") {
				t.Error("Token missing se (SignedExpiry) parameter")
			}
			if !strings.Contains(token, "skn=") {
				t.Error("Token missing skn (SignedKeyName) parameter")
			}
		})
	}
}

// TestCreateRelayURL verifies relay URL construction
func TestCreateRelayURL(t *testing.T) {
	tests := []struct {
		name             string
		namespace        string
		hybridConnection string
		action           string
		sasToken         string
		wantContains     []string
	}{
		{
			name:             "connect URL",
			namespace:        "test-relay.servicebus.windows.net",
			hybridConnection: "test-hc",
			action:           "connect",
			sasToken:         "SharedAccessSignature sr=test&sig=test&se=123&skn=key",
			wantContains: []string{
				"wss://test-relay.servicebus.windows.net",
				"/$hc/test-hc",
				"sb-hc-action=connect",
				"sb-hc-token=",
			},
		},
		{
			name:             "listen URL",
			namespace:        "test-relay.servicebus.windows.net",
			hybridConnection: "test-hc-events",
			action:           "listen",
			sasToken:         "SharedAccessSignature sr=test&sig=test&se=123&skn=key",
			wantContains: []string{
				"wss://test-relay.servicebus.windows.net",
				"/$hc/test-hc-events",
				"sb-hc-action=listen",
				"sb-hc-token=",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			url := CreateRelayURL(
				tt.namespace,
				tt.hybridConnection,
				tt.action,
				tt.sasToken,
			)

			for _, want := range tt.wantContains {
				if !strings.Contains(url, want) {
					t.Errorf("URL missing required component %q\nGot: %s", want, url)
				}
			}

			// Verify it's a WebSocket URL
			if !strings.HasPrefix(url, "wss://") {
				t.Errorf("URL should start with wss://, got: %s", url)
			}
		})
	}
}

// BenchmarkCreateSASToken benchmarks SAS token generation
func BenchmarkCreateSASToken(b *testing.B) {
	namespace := "test-namespace.servicebus.windows.net"
	entityPath := "test-hc"
	keyName := "RootManageSharedAccessKey"
	key := "testkey123"

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_, _ = CreateSASToken(namespace, entityPath, keyName, key, 3600)
	}
}
