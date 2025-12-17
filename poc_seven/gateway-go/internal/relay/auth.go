package relay

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"net/url"
	"time"
)

// CreateSASToken generates an Azure Relay SAS (Shared Access Signature) token.
// This MUST match the Python implementation exactly for authentication to work.
//
// Python implementation (relay_event_sender.py):
//
//	def create_sas_token(namespace: str, entity_path: str, key_name: str, key: str, expiry_seconds: int = 3600) -> str:
//	    uri = f"http://{namespace}/{entity_path}"
//	    encoded_uri = urllib.parse.quote_plus(uri)
//	    expiry = str(int(time.time() + expiry_seconds))
//	    signature = base64.b64encode(
//	        hmac.new(key.encode(), f"{encoded_uri}\n{expiry}".encode(), hashlib.sha256).digest()
//	    )
//	    return f"SharedAccessSignature sr={encoded_uri}&sig={urllib.parse.quote_plus(signature)}&se={expiry}&skn={key_name}"
func CreateSASToken(namespace, entityPath, keyName, key string, expirySeconds int) (string, error) {
	// Step 1: Construct URI (must use http:// not https://)
	uri := fmt.Sprintf("http://%s/%s", namespace, entityPath)

	// Step 2: URL encode the URI (Python's quote_plus)
	encodedURI := url.QueryEscape(uri)

	// Step 3: Calculate expiry timestamp
	expiry := time.Now().Unix() + int64(expirySeconds)
	expiryStr := fmt.Sprintf("%d", expiry)

	// Step 4: Create string to sign: "{encoded_uri}\n{expiry}"
	stringToSign := fmt.Sprintf("%s\n%s", encodedURI, expiryStr)

	// Step 5: HMAC-SHA256 signature
	h := hmac.New(sha256.New, []byte(key))
	h.Write([]byte(stringToSign))
	signature := h.Sum(nil)

	// Step 6: Base64 encode the signature
	encodedSignature := base64.StdEncoding.EncodeToString(signature)

	// Step 7: URL encode the base64 signature (Python's quote_plus)
	encodedSig := url.QueryEscape(encodedSignature)

	// Step 8: Build the SAS token
	token := fmt.Sprintf(
		"SharedAccessSignature sr=%s&sig=%s&se=%s&skn=%s",
		encodedURI,
		encodedSig,
		expiryStr,
		keyName,
	)

	return token, nil
}

// CreateRelayURL creates the WebSocket URL for Azure Relay connection.
// For sender (connect action):
//
//	wss://{namespace}/$hc/{connection}?sb-hc-action=connect&sb-hc-token={token}
//
// For listener (listen action):
//
//	wss://{namespace}/$hc/{connection}?sb-hc-action=listen&sb-hc-token={token}
func CreateRelayURL(namespace, hybridConnection, action, sasToken string) string {
	// URL encode the SAS token
	encodedToken := url.QueryEscape(sasToken)

	return fmt.Sprintf(
		"wss://%s/$hc/%s?sb-hc-action=%s&sb-hc-token=%s",
		namespace,
		hybridConnection,
		action,
		encodedToken,
	)
}
