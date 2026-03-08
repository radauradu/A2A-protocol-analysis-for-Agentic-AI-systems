#!/bin/bash
# Quick test script to verify post-processing works
# This processes existing tool_evaluations CSV files
# Usage: ./test_processing.sh [profile]

set -e

PROFILE=${1:-"two-env"}

echo "=========================================="
echo "Testing Post-Processing Script"
echo "Profile: $PROFILE"
echo "=========================================="

# Determine which container to use based on profile
if [ "$PROFILE" = "env3-only" ]; then
    CONTAINER="env3"
elif [ "$PROFILE" = "two-env" ]; then
    CONTAINER="env1"
else
    echo "[WARNING] Unknown profile '$PROFILE', defaulting to env1"
    CONTAINER="env1"
fi

echo "Using container: $CONTAINER"

# Check if container is running
if ! docker compose --profile "$PROFILE" ps "$CONTAINER" | grep -q "Up"; then
    echo "[INFO] Container $CONTAINER is not running. Starting it..."
    docker compose --profile "$PROFILE" up -d "$CONTAINER"
    echo "[INFO] Waiting for container to be ready..."
    sleep 5
fi

# Copy processing script into container
echo "[INFO] Copying process_jmeter_results.py to $CONTAINER container..."
docker compose --profile "$PROFILE" cp process_jmeter_results.py "$CONTAINER:/app/process_jmeter_results.py"

# Check if we have existing data
if [ ! -f "3Hour_Radu/1_1/tool_evaluations_1.csv" ]; then
    echo "[WARNING] No test data found at 3Hour_Radu/1_1/tool_evaluations_1.csv"
    echo "[INFO] Will test with --all option instead"
    TEST_MODE="all"
else
    TEST_MODE="single"
fi

echo ""
echo "[TEST] Processing existing tool_evaluations files..."

# Test 1: Process a specific file
if [ "$TEST_MODE" = "single" ] && [ -f "3Hour_Radu/1_1/tool_evaluations_1.csv" ]; then
    echo ""
    echo "[TEST 1] Processing single file: 3Hour_Radu/1_1/tool_evaluations_1.csv"
    docker compose --profile "$PROFILE" exec "$CONTAINER" python /app/process_jmeter_results.py \
        --csv "/app/3Hour_Radu/1_1/tool_evaluations_1.csv" \
        --users 1 \
        --nodes 1
    
    if [ -f "3Hour_Radu/1_1/energy_consumption.png" ]; then
        echo "✅ [TEST 1 PASSED] Graph generated: 3Hour_Radu/1_1/energy_consumption.png"
    else
        echo "❌ [TEST 1 FAILED] Graph not generated"
        exit 1
    fi
fi

# Test 2: Process all files
echo ""
echo "[TEST 2] Processing all tool_evaluations files..."
docker compose --profile "$PROFILE" exec "$CONTAINER" python /app/process_jmeter_results.py --all

# Test 3: Process JMeter outputs
echo ""
echo "[TEST 3] Processing JMeter raw output files..."
docker compose --profile "$PROFILE" exec "$CONTAINER" python /app/process_jmeter_results.py --jmeter-only

echo ""
echo "=========================================="
echo "✅ All tests passed!"
echo "Check 3Hour_Radu/*/ for generated graphs"
echo "=========================================="

