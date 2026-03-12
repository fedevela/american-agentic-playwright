#!/bin/bash
# OpenClaw SDLC Phase Runner
# Usage: ./run_phase.sh <phase_number> <issue_or_context>

PHASE=${1:-1}
CONTEXT="${*:2}"

echo "=========================================="
echo "OpenClaw SDLC - Phase $PHASE"
echo "=========================================="
echo "Context: $CONTEXT"
echo ""

# Update state
STATE_FILE=".openhands/workspace/.sdlc-state.json"
mkdir -p "$(dirname "$STATE_FILE")"
cat > "$STATE_FILE" << STATE_EOF
{
  "current_phase": $PHASE,
  "current_step": 0,
  "last_issue": null,
  "last_context": "$CONTEXT",
  "artifacts": {}
}
STATE_EOF

echo "Updated state: $STATE_FILE"
echo ""

# Route to OpenHands based on phase type
case $PHASE in
  1|2|3|4)
    echo "Phase $PHASE is discussion-only (GitHub comment output)."
    echo "Use trigger.py for automatic execution from GitHub labels."
    ;;
  5|6|7|8|9)
    echo "Triggering OpenHands workflow for Phase $PHASE..."
    echo ""
    echo "Note: Full OpenHands integration requires:"
    echo "  1. OpenHands API key in GitHub secrets"
    echo "  2. Proper OpenHands agent configuration"
    echo ""
    echo "For testing, use:"
    echo "  python trigger.py --label phase:<phase> --issue <number>"
    ;;
  *)
    echo "Unknown phase: $PHASE"
    exit 1
    ;;
esac
