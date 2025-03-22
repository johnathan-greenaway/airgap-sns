#!/bin/bash

# Parse command line arguments
URL=""
PROXY=""
ENCRYPT=false
PASSWORD=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --url) URL="$2"; shift ;;
        --proxy) PROXY="$2"; shift ;;
        --encrypt) ENCRYPT=true ;;
        --encrypt-password) PASSWORD="$2"; shift ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

# Start Airgap SNS server
uvicorn airgap_sns.host.server:app --host 0.0.0.0 --port 9000 &
SERVER_PID=$!
echo "Started Airgap SNS server (PID: $SERVER_PID)"

# Wait for server to start
sleep 3

# Start scraper module with configured options
SCRAPER_CMD="python -m airgap_sns.core.web_scraper --id scraper --uri ws://localhost:9000/ws/"
if [ -n "$URL" ]; then
    SCRAPER_CMD+=" --url $URL"
fi
if [ -n "$PROXY" ]; then
    SCRAPER_CMD+=" --proxy $PROXY"
fi
if [ "$ENCRYPT" = true ]; then
    SCRAPER_CMD+=" --encrypt"
    if [ -n "$PASSWORD" ]; then
        SCRAPER_CMD+=" --encrypt-password $PASSWORD"
    fi
fi

eval $SCRAPER_CMD &
SCRAPER_PID=$!
echo "Started scraper module (PID: $SCRAPER_PID)"

# Start interactive client
python -m airgap_sns.client.client --id user123 --uri ws://localhost:9000/ws/ --interactive

# Cleanup
kill $SCRAPER_PID
kill $SERVER_PID