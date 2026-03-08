#!/bin/bash
# Automated JMeter test runner with post-processing
# Usage: ./run_jmeter_with_processing.sh [profile] [test_file] [target_host] [target_path] [nodes] [users]

set -e

PROFILE=${1:-"two-env"}
TEST_FILE=${2:-"ReqVM3.jmx"}

# Set defaults based on profile
if [ "$PROFILE" = "env3-only" ]; then
    DEFAULT_HOST="env3"
    DEFAULT_PATH="/env3-openai-agents"
    DEFAULT_TEST_FILE="ReqVM3_env3.jmx"
else
    DEFAULT_HOST="env1"
    DEFAULT_PATH="/env1-then-env2-a2a"
    DEFAULT_TEST_FILE="ReqVM3.jmx"
fi

TARGET_HOST=${3:-"$DEFAULT_HOST"}
TARGET_PATH=${4:-"$DEFAULT_PATH"}
TEST_FILE=${2:-"$DEFAULT_TEST_FILE"}
NODES=${5:-1}
USERS=${6:-1}

echo "=========================================="
echo "JMeter Test Runner with Auto-Processing"
echo "=========================================="
echo "Profile: $PROFILE"
echo "Test File: $TEST_FILE"
echo "Target: $TARGET_HOST$TARGET_PATH"
echo "Nodes: $NODES, Users: $USERS"
echo "=========================================="

# Determine results directory based on profile
if [ "$PROFILE" = "env3-only" ]; then
    RESULTS_DIR="/results_non_a2a"
    BASE_DIR="3Hour_Radu_nonA2A"
else
    RESULTS_DIR="/results_a2a"
    BASE_DIR="3Hour_Radu"
fi

# Run JMeter test
echo ""
echo "[1/2] Running JMeter test..."
docker compose --profile "$PROFILE" exec jmeter jmeter -n -t "/tests/$TEST_FILE" \
  -Jtarget.host="$TARGET_HOST" \
  -Jtarget.path="$TARGET_PATH" \
  -Jcsv.path=/tests/prompts_for_jmeter.csv \
  -Jresults.dir="$RESULTS_DIR" \
  -Jnodes="$NODES" \
  -Jusers="$USERS"

JMETER_EXIT_CODE=$?

if [ $JMETER_EXIT_CODE -ne 0 ]; then
    echo "[ERROR] JMeter test failed with exit code $JMETER_EXIT_CODE"
    exit $JMETER_EXIT_CODE
fi

echo ""
echo "[2/2] Processing results and generating graphs..."

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

# Copy processing script into container (if not already there)
docker compose --profile "$PROFILE" cp process_jmeter_results.py "$CONTAINER:/app/process_jmeter_results.py" 2>/dev/null || true

# Process results (run in appropriate container which has Python and dependencies)
docker compose --profile "$PROFILE" exec "$CONTAINER" python /app/process_jmeter_results.py --all --base-dir "$BASE_DIR"

echo ""
echo "=========================================="
echo "✅ Complete! Check $BASE_DIR/ for graphs"
echo "=========================================="

