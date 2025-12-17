package relay

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/gorilla/websocket"
	"go.uber.org/zap"
	"screening-gateway/internal/storage"
)

// Listener listens for worklist actions from Django via Azure Relay
type Listener struct {
	namespace        string
	hybridConnection string
	keyName          string
	key              string
	storage          *storage.WorklistStorage
	logger           *zap.Logger
}

// NewListener creates a new relay listener
func NewListener(
	namespace, hybridConnection, keyName, key string,
	worklistStorage *storage.WorklistStorage,
	logger *zap.Logger,
) *Listener {
	return &Listener{
		namespace:        namespace,
		hybridConnection: hybridConnection,
		keyName:          keyName,
		key:              key,
		storage:          worklistStorage,
		logger:           logger,
	}
}

// AcceptMessage represents the rendezvous accept message from Azure Relay
type AcceptMessage struct {
	Accept struct {
		Address string `json:"address"`
	} `json:"accept"`
}

// Listen starts listening for worklist actions from Django
// This is a blocking call that runs until context is cancelled
// Auto-reconnects on connection failure with 5-second retry
func (l *Listener) Listen(ctx context.Context) error {
	for {
		select {
		case <-ctx.Done():
			l.logger.Info("Listener shutting down")
			return ctx.Err()
		default:
		}

		err := l.listenOnce(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return ctx.Err()
			}

			l.logger.Error("Listener connection error, retrying in 5 seconds",
				zap.Error(err),
			)

			// Wait 5 seconds before reconnecting
			select {
			case <-time.After(5 * time.Second):
			case <-ctx.Done():
				return ctx.Err()
			}
		}
	}
}

// listenOnce establishes a connection and listens for messages until error
func (l *Listener) listenOnce(ctx context.Context) error {
	// Create SAS token
	sasToken, err := CreateSASToken(l.namespace, l.hybridConnection, l.keyName, l.key, 3600)
	if err != nil {
		return fmt.Errorf("failed to create SAS token: %w", err)
	}

	// Create WebSocket URL for listener (listen action)
	url := CreateRelayURL(l.namespace, l.hybridConnection, "listen", sasToken)

	l.logger.Info("Connecting to Azure Relay",
		zap.String("hybrid_connection", l.hybridConnection),
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

	l.logger.Info("Connected to Azure Relay - waiting for worklist actions")

	// Listen for incoming messages
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		// Read message from relay
		messageType, messageData, err := conn.ReadMessage()
		if err != nil {
			return fmt.Errorf("failed to read message: %w", err)
		}

		if messageType != websocket.TextMessage {
			l.logger.Warn("Unexpected message type",
				zap.Int("type", messageType),
			)
			continue
		}

		// Parse accept message
		var acceptMsg AcceptMessage
		if err := json.Unmarshal(messageData, &acceptMsg); err != nil {
			l.logger.Warn("Failed to parse accept message",
				zap.Error(err),
				zap.String("message", string(messageData)),
			)
			continue
		}

		// Check if this is an accept message with rendezvous URL
		if acceptMsg.Accept.Address == "" {
			l.logger.Warn("Received message without accept.address",
				zap.String("message", string(messageData)),
			)
			continue
		}

		l.logger.Info("Incoming connection from Django",
			zap.String("address", acceptMsg.Accept.Address),
		)

		// Handle the rendezvous connection in a goroutine
		go l.handleRendezvous(ctx, acceptMsg.Accept.Address)
	}
}

// handleRendezvous connects to the rendezvous URL and processes the worklist action
func (l *Listener) handleRendezvous(ctx context.Context, rendezvousURL string) {
	// Create WebSocket dialer
	dialer := websocket.DefaultDialer
	dialer.EnableCompression = false
	dialer.HandshakeTimeout = 10 * time.Second

	// Connect to rendezvous URL
	conn, resp, err := dialer.DialContext(ctx, rendezvousURL, nil)
	if err != nil {
		if resp != nil {
			l.logger.Error("Failed to connect to rendezvous URL",
				zap.String("url", rendezvousURL),
				zap.Int("status", resp.StatusCode),
				zap.Error(err),
			)
		} else {
			l.logger.Error("Failed to connect to rendezvous URL",
				zap.String("url", rendezvousURL),
				zap.Error(err),
			)
		}
		return
	}
	defer conn.Close()

	// Set read deadline (30 seconds like Python)
	if err := conn.SetReadDeadline(time.Now().Add(30 * time.Second)); err != nil {
		l.logger.Error("Failed to set read deadline", zap.Error(err))
		return
	}

	// Read the worklist action message
	messageType, messageData, err := conn.ReadMessage()
	if err != nil {
		l.logger.Error("Failed to read message from rendezvous",
			zap.Error(err),
		)
		return
	}

	if messageType != websocket.TextMessage {
		l.logger.Warn("Unexpected message type from rendezvous",
			zap.Int("type", messageType),
		)
		return
	}

	// Parse worklist action
	var action WorklistAction
	if err := json.Unmarshal(messageData, &action); err != nil {
		l.logger.Error("Failed to parse worklist action",
			zap.Error(err),
			zap.String("message", string(messageData)),
		)

		// Send error response
		errResponse := RelayResponse{
			Status:  "parse_error",
			Message: err.Error(),
		}
		l.sendResponse(conn, &errResponse)
		return
	}

	// Process the action
	response := l.processWorklistAction(&action)

	// Send acknowledgment
	if err := l.sendResponse(conn, response); err != nil {
		l.logger.Error("Failed to send response",
			zap.Error(err),
		)
	}
}

// processWorklistAction processes a worklist action and creates a database entry
// Matches Python process_worklist_action() behavior
func (l *Listener) processWorklistAction(action *WorklistAction) *RelayResponse {
	if action.ActionType == "worklist.create_item" {
		item := action.Parameters.WorklistItem

		// Create worklist item in database
		worklistItem := &storage.WorklistItem{
			AccessionNumber:  item.AccessionNumber,
			PatientID:        item.Participant.NHSNumber,
			PatientName:      item.Participant.Name,
			PatientBirthDate: item.Participant.BirthDate,
			PatientSex:       item.Participant.Sex,
			ScheduledDate:    item.Scheduled.Date,
			ScheduledTime:    item.Scheduled.Time,
			Modality:         item.Procedure.Modality,
			StudyDescription: storage.NewNullString(item.Procedure.StudyDescription),
			Status:           storage.WorklistStatusScheduled,
			SourceMessageID:  storage.NewNullString(action.ActionID),
		}

		if err := l.storage.AddWorklistItem(worklistItem); err != nil {
			l.logger.Error("Failed to create worklist item",
				zap.String("accession_number", item.AccessionNumber),
				zap.Error(err),
			)
			return &RelayResponse{
				Status:  "database_error",
				Message: err.Error(),
			}
		}

		l.logger.Info("Created worklist item",
			zap.String("accession_number", item.AccessionNumber),
			zap.String("action_id", action.ActionID),
		)

		return &RelayResponse{
			Status:  "created",
			Message: fmt.Sprintf("Created worklist item: %s", item.AccessionNumber),
		}
	}

	l.logger.Warn("Unknown action type",
		zap.String("action_type", action.ActionType),
	)

	return &RelayResponse{
		Status:  "unknown_action",
		Message: fmt.Sprintf("Unknown action type: %s", action.ActionType),
	}
}

// sendResponse sends a JSON response to the WebSocket connection
func (l *Listener) sendResponse(conn *websocket.Conn, response *RelayResponse) error {
	responseJSON, err := json.Marshal(response)
	if err != nil {
		return fmt.Errorf("failed to marshal response: %w", err)
	}

	// Set write deadline
	if err := conn.SetWriteDeadline(time.Now().Add(10 * time.Second)); err != nil {
		return fmt.Errorf("failed to set write deadline: %w", err)
	}

	if err := conn.WriteMessage(websocket.TextMessage, responseJSON); err != nil {
		return fmt.Errorf("failed to write response: %w", err)
	}

	return nil
}
