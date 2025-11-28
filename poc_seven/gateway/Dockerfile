# Dockerfile for Orthanc-based Modality Worklist Server
# POC Six - Gateway MWL Server

FROM orthancteam/orthanc:25.11.0

# Install uv for fast package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install sqlite3 and Python dependencies
RUN apt-get update && \
    apt-get install -y sqlite3 && \
    UV_BREAK_SYSTEM_PACKAGES=1 uv pip install --system --no-cache \
        pydicom==3.0.1 \
        pynetdicom==3.0.4 \
        websockets==15.0.1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create necessary directories
RUN mkdir -p /scripts /var/lib/orthanc/db /var/log/orthanc

# Copy the Python worklist server scripts
COPY scripts/worklist_server.py /scripts/worklist_server.py
COPY scripts/worklist_storage.py /scripts/worklist_storage.py
COPY scripts/relay_listener.py /scripts/relay_listener.py
COPY scripts/relay_event_sender.py /scripts/relay_event_sender.py
COPY scripts/init_db.sql /scripts/init_db.sql

# Copy Orthanc configuration
COPY orthanc.json /etc/orthanc/orthanc.json

# Copy and set up the entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Expose ports:
# 8042 - Orthanc HTTP/REST API
# 4242 - Orthanc DICOM port
# 4243 - Worklist/MPPS DICOM port
EXPOSE 8042 4242 4243

# Set environment variables
ENV ORTHANC_CONFIG=/etc/orthanc/orthanc.json

# Use the entrypoint script to initialize DB and start Orthanc
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["/etc/orthanc/orthanc.json"]
