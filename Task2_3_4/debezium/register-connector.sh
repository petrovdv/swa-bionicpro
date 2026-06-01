#!/bin/sh
set -e

echo '=== Debezium connector registration ==='

# Wait for Kafka Connect
echo 'Waiting for Kafka Connect...'
for i in $(seq 1 50); do
  if curl -sf http://kafka-connect:8083/ > /dev/null 2>&1; then
    echo '✓ Kafka Connect ready'
    break
  fi
  echo "  Attempt $i/50..."
  sleep 2
done

# Register connector
echo 'Registering connector...'
HTTP_CODE=$(curl -s -X POST http://kafka-connect:8083/connectors \
  -H "Content-Type: application/json" \
  -d @/config/connector.json \
  -w "\n%{http_code}" \
  -o /tmp/resp.json)

HTTP_CODE=$(echo "$HTTP_CODE" | tail -n1)

if [ "$HTTP_CODE" = "201" ] || [ "$HTTP_CODE" = "409" ]; then
  echo "OK (HTTP $HTTP_CODE)"
  exit 0
else
  echo "Failed (HTTP $HTTP_CODE)"
  cat /tmp/resp.json 2>/dev/null || true
  exit 1
fi