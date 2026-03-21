#!/bin/bash

# Default number of executions
N=${1:-5}

echo "Running trigger.py $N times..."

for i in $(seq 1 $N); do
  echo "--- Execution $i of $N ---"
  python3 trigger.py
  EXIT_CODE=$?
  if [ $EXIT_CODE -ne 0 ]; then
    echo "Execution $i failed with exit code $EXIT_CODE. Stopping."
    exit $EXIT_CODE
  fi
done

echo "All $N executions completed successfully."
