package relay

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"
)

// Sender sends events to Django via Azure Relay
type Sender struct {
	namespace        string
	hybridConnection string
	keyName          string
	key              string
	logger           *zap.Logger
}

// NewSender creates a new relay sender
func NewSender(namespace, hybridConnection, keyName, key string, logger *zap.Logger) *Sender {
	return &Sender{
		namespace:        namespace,
		hybridConnection: hybridConnection,
		keyName:          keyName,
		key:              key,
		logger:           logger,
	}
}

// SendMPPSEvent sends an MPPS status update event to Django
// Uses rendezvous pattern: creates fresh connection, sends, waits for ack, closes
// Matches Python send_mpps_event() behavior
func (s *Sender) SendMPPSEvent(ctx context.Context, event *MPPSEvent) error {
	// Marshal event to JSON
	eventJSON, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("failed to marshal MPPS event: %w", err)
	}

	// Send with retry logic
	return s.sendWithRetry(ctx, eventJSON, "MPPS", 3)
}

// SendImageEvent sends an image_received event to Django
// Uses rendezvous pattern: creates fresh connection, sends, waits for ack, closes
// Matches Python send_image_event() behavior
func (s *Sender) SendImageEvent(ctx context.Context, event *ImageReceivedMessage) error {
	// Marshal event to JSON
	eventJSON, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("failed to marshal image event: %w", err)
	}

	// Send with retry logic
	return s.sendWithRetry(ctx, eventJSON, "image", 3)
}

// sendWithRetry sends a message with exponential backoff retry
func (s *Sender) sendWithRetry(ctx context.Context, message []byte, eventType string, maxRetries int) error {
	var lastErr error

	for attempt := 0; attempt < maxRetries; attempt++ {
		if attempt > 0 {
			// Exponential backoff: 1s, 2s, 4s
			backoff := time.Duration(1<<uint(attempt-1)) * time.Second
			s.logger.Info("Retrying relay send after backoff",
				zap.String("event_type", eventType),
				zap.Int("attempt", attempt+1),
				zap.Duration("backoff", backoff),
			)

			select {
			case <-time.After(backoff):
			case <-ctx.Done():
				return ctx.Err()
			}
		}

		// Try to send
		err := s.send(ctx, message, eventType)
		if err == nil {
			return nil // Success!
		}

		lastErr = err
		s.logger.Warn("Relay send attempt failed",
			zap.String("event_type", eventType),
			zap.Int("attempt", attempt+1),
			zap.Int("max_retries", maxRetries),
			zap.Error(err),
		)
	}

	return fmt.Errorf("failed after %d retries: %w", maxRetries, lastErr)
}

// send sends a message using the Azure Relay rendezvous pattern
// CRITICAL: This MUST match Python behavior exactly
func (s *Sender) send(ctx context.Context, message []byte, eventType string) error {
	// Create SAS token (expires in 1 hour)
	sasToken, err := CreateSASToken(s.namespace, s.hybridConnection, s.keyName, s.key, 3600)
	if err != nil {
		return fmt.Errorf("failed to create SAS token: %w", err)
	}

	// Create WebSocket URL for sender (connect action)
	url := CreateRelayURL(s.namespace, s.hybridConnection, "connect", sasToken)

	s.logger.Debug("Connecting to Azure Relay",
		zap.String("hybrid_connection", s.hybridConnection),
		zap.String("event_type", eventType),
	)

	// Create WebSocket dialer
	dialer := websocket.DefaultDialer

	// CRITICAL: Disable compression to match Python (compression=None)
	dialer.EnableCompression = false

	// Set handshake timeout
	dialer.HandshakeTimeout = 10 * time.Second

	// Connect to relay
	conn, resp, err := dialer.DialContext(ctx, url, nil)
	if err != nil {
		if resp != nil {
			return fmt.Errorf("failed to connect to relay (status %d): %w", resp.StatusCode, err)
		}
		return fmt.Errorf("failed to connect to relay: %w", err)
	}
	defer conn.Close()

	s.logger.Info("Connected to Azure Relay",
		zap.String("event_type", eventType),
	)

	// Set write deadline
	if err := conn.SetWriteDeadline(time.Now().Add(10 * time.Second)); err != nil {
		return fmt.Errorf("failed to set write deadline: %w", err)
	}

	// Send the message
	if err := conn.WriteMessage(websocket.TextMessage, message); err != nil {
		return fmt.Errorf("failed to send message: %w", err)
	}

	s.logger.Info("Sent event to Django",
		zap.String("event_type", eventType),
		zap.Int("size", len(message)),
	)

	// Wait for acknowledgment with timeout
	if err := conn.SetReadDeadline(time.Now().Add(10 * time.Second)); err != nil {
		return fmt.Errorf("failed to set read deadline: %w", err)
	}

	messageType, ackData, err := conn.ReadMessage()
	if err != nil {
		return fmt.Errorf("failed to receive acknowledgment: %w", err)
	}

	if messageType != websocket.TextMessage {
		return fmt.Errorf("unexpected message type: %d", messageType)
	}

	// Parse acknowledgment
	var response RelayResponse
	if err := json.Unmarshal(ackData, &response); err != nil {
		return fmt.Errorf("failed to parse acknowledgment: %w", err)
	}

	s.logger.Info("Received acknowledgment from Django",
		zap.String("event_type", eventType),
		zap.String("status", response.Status),
		zap.String("message", response.Message),
	)

	// Validate response status (matches Python logic)
	if eventType == "MPPS" {
		// Valid MPPS responses: updated, action_not_found, appointment_not_found
		if response.Status == "updated" ||
		   response.Status == "action_not_found" ||
		   response.Status == "appointment_not_found" {
			return nil
		}
		if response.Status == "error" || response.Status == "unknown_status" {
			return fmt.Errorf("Django reported error: %s - %s", response.Status, response.Message)
		}
		// Unexpected but not necessarily an error
		s.logger.Warn("Django reported unexpected status",
			zap.String("status", response.Status),
		)
		return nil
	}

	if eventType == "image" {
		// Valid image responses: created, already_exists
		if response.Status == "created" || response.Status == "already_exists" {
			return nil
		}
		return fmt.Errorf("Django reported non-success status: %s - %s", response.Status, response.Message)
	}

	// Unknown event type - just check it's not an error
	if response.Status == "error" {
		return fmt.Errorf("Django reported error: %s", response.Message)
	}

	return nil
}

// SendMPPSEventSync is a convenience wrapper for sending MPPS events synchronously
// Uses a background context with 30-second timeout
func (s *Sender) SendMPPSEventSync(actionID, accessionNumber, status string, mppsInstanceUID *string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	event := NewMPPSEvent(actionID, accessionNumber, status, mppsInstanceUID)
	return s.SendMPPSEvent(ctx, event)
}

// SendImageEventSync is a convenience wrapper for sending image events synchronously
// Uses a background context with 30-second timeout
func (s *Sender) SendImageEventSync(event *ImageReceivedMessage) error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	return s.SendImageEvent(ctx, event)
}
