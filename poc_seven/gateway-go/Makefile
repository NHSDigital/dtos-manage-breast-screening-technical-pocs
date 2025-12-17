.PHONY: build test coverage clean fmt lint help docker-build docker-up docker-down docker-logs docker-clean

# Build all binaries
build:
	@echo "Building all services..."
	@mkdir -p bin
	go build -o bin/worklist-server ./cmd/worklist-server || echo "worklist-server not yet implemented"
	go build -o bin/pacs-server ./cmd/pacs-server || echo "pacs-server not yet implemented"
	go build -o bin/relay-listener ./cmd/relay-listener || echo "relay-listener not yet implemented"
	go build -o bin/image-processor ./cmd/image-processor || echo "image-processor not yet implemented"
	@echo "Build complete!"

# Run all tests
test:
	@echo "Running tests..."
	go test -v ./...

# Run tests with coverage
coverage:
	@echo "Running tests with coverage..."
	go test -v -coverprofile=coverage.out ./...
	go tool cover -html=coverage.out -o coverage.html
	@echo "Coverage report generated: coverage.html"

# Run benchmarks
bench:
	@echo "Running benchmarks..."
	go test -bench=. -benchmem ./internal/storage/...

# Format code
fmt:
	@echo "Formatting code..."
	go fmt ./...
	@echo "Code formatted!"

# Run linter (requires golangci-lint)
lint:
	@echo "Running linter..."
	@which golangci-lint > /dev/null || (echo "golangci-lint not installed. Install with: brew install golangci-lint" && exit 1)
	golangci-lint run ./...

# Clean build artifacts
clean:
	@echo "Cleaning..."
	rm -rf bin/
	rm -f coverage.out coverage.html
	@echo "Clean complete!"

# Download dependencies
deps:
	@echo "Downloading dependencies..."
	go mod download
	go mod tidy
	@echo "Dependencies downloaded!"

# Verify dependencies
verify:
	@echo "Verifying dependencies..."
	go mod verify
	@echo "Dependencies verified!"

# Run tests and show coverage percentage
test-short:
	@echo "Running tests..."
	go test -short -cover ./...

# Docker Commands
docker-build:
	@echo "Building Docker images..."
	docker-compose build

docker-up:
	@echo "Starting services with Docker Compose..."
	docker-compose up -d
	@echo "Services started! Use 'make docker-logs' to view logs"

docker-down:
	@echo "Stopping Docker services..."
	docker-compose down

docker-logs:
	@echo "Following logs (Ctrl+C to exit)..."
	docker-compose logs -f

docker-restart:
	@echo "Restarting Docker services..."
	docker-compose restart

docker-ps:
	@echo "Service status:"
	docker-compose ps

docker-clean:
	@echo "Stopping and removing all containers, networks, and volumes..."
	docker-compose down -v
	@echo "Docker cleanup complete!"

# Build and run in one command
docker-start: docker-build docker-up

# Help
help:
	@echo "Available targets:"
	@echo ""
	@echo "Build & Test:"
	@echo "  build        - Build all service binaries"
	@echo "  test         - Run all tests with verbose output"
	@echo "  coverage     - Run tests and generate HTML coverage report"
	@echo "  bench        - Run benchmarks"
	@echo "  test-short   - Run tests with coverage percentage"
	@echo ""
	@echo "Code Quality:"
	@echo "  fmt          - Format code with go fmt"
	@echo "  lint         - Run golangci-lint"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build   - Build all Docker images"
	@echo "  docker-up      - Start services in detached mode"
	@echo "  docker-down    - Stop all services"
	@echo "  docker-logs    - Follow logs from all services"
	@echo "  docker-restart - Restart all services"
	@echo "  docker-ps      - Show service status"
	@echo "  docker-clean   - Stop and remove everything (including volumes)"
	@echo "  docker-start   - Build and start services (build + up)"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean        - Remove build artifacts"
	@echo "  deps         - Download and tidy dependencies"
	@echo "  verify       - Verify dependencies"
	@echo "  help         - Show this help message"
