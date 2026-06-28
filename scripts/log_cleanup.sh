#!/bin/bash
# log_cleanup.sh - Cleanup old log files and rotate large logs

LOG_DIR="${1:-./logs}"
DAYS_TO_KEEP=7
MAX_SIZE_MB=10

if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR"
fi

echo "Starting log cleanup in: $LOG_DIR"

# 1. Delete log files older than 7 days
find "$LOG_DIR" -type f -name "*.log" -mtime +$DAYS_TO_KEEP -exec rm -f {} \;
echo "Deleted logs older than $DAYS_TO_KEEP days."

# 2. Rotate log files larger than 10MB
find "$LOG_DIR" -type f -name "*.log" -size +${MAX_SIZE_MB}M | while read -r log_file; do
    echo "Rotating large log file: $log_file"
    # Compress the file
    gzip -c "$log_file" > "${log_file}.$(date +%Y%m%d%H%M%S).gz"
    # Clear the original file
    cat /dev/null > "$log_file"
done

echo "Log cleanup completed."
