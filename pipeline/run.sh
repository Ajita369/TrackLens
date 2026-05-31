#!/bin/bash
set -e

# Run directory path configuration
DATA_DIR="${DATA_DIR:-./data}"
OUTPUT_DIR="${OUTPUT_DIR:-./data/output}"

echo "Starting TrackLens Detection Pipeline..."
python -m pipeline.run --data-dir "$DATA_DIR" --output-dir "$OUTPUT_DIR" --skip-frames 2

echo "Pipeline execution completed."
echo "Generated events file: $OUTPUT_DIR/ST1008/events.jsonl"
