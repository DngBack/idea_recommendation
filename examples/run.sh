#!/usr/bin/env bash
# =============================================
# Example: generate ideas from a topic file
# =============================================
# Make sure you have set your API key(s):
#   export OPENAI_API_KEY="sk-..."
#   export S2_API_KEY="..."          # optional, for Semantic Scholar
#
# Run from the Des/ root directory (or wherever this project lives).

set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Idea Generator – Example Run ==="

# Option 1: Run as a module
python -m idea_generator \
    --topic-file topics/example_icbinb.md \
    --config config/default.yaml \
    --model gpt-4o-2024-05-13 \
    --max-generations 3 \
    --num-reflections 3 \
    --output output/icbinb_ideas.json \
    --verbose

echo ""
echo "Done! Check output/icbinb_ideas.json for the generated ideas."
