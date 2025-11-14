# Dockerfile for Orthanc-based Modality Worklist Server
# POC Six - Gateway MWL Server

FROM orthancteam/orthanc:25.11.0

# Install Python dependencies for the worklist server
RUN apt-get update && \
    apt-get install -y python3-pip && \
    pip3 install --no-cache-dir --break-system-packages \
        pydicom==3.0.1 \
        pynetdicom==3.0.4 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Create necessary directories
RUN mkdir -p /scripts /var/lib/orthanc/db /var/log/orthanc

# Copy the Python worklist server script
COPY scripts/worklist_server.py /scripts/worklist_server.py

# Copy Orthanc configuration
COPY orthanc.json /etc/orthanc/orthanc.json

# Expose ports:
# 8042 - Orthanc HTTP/REST API
# 4242 - Orthanc DICOM port
# 4243 - Worklist/MPPS DICOM port
EXPOSE 8042 4242 4243

# Set environment variables
ENV ORTHANC_CONFIG=/etc/orthanc/orthanc.json

# Run Orthanc with the configuration file
CMD ["/etc/orthanc/orthanc.json"]
