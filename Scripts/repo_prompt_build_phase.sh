#!/bin/bash
# Xcode build phase script – Repo-Prompt integration (Step 1.10)
#
# This script generates an XML prompt of the current source tree and writes
# the LLM diff suggestions to *DerivedData/RepoPrompt/*. Review the output
# after each build and apply patches as needed.
#
# **Usage**: Add as a "Run Script" phase in your target's Build Phases:
#   Shell: /bin/bash
#   Script: ${PROJECT_DIR}/Scripts/repo_prompt_build_phase.sh

REPO_ROOT="${PROJECT_DIR}"
OUTPUT_DIR="${BUILT_PRODUCTS_DIR}/../RepoPrompt"
mkdir -p "${OUTPUT_DIR}"

# SECURITY: Input sanitisation – avoid globbing edge cases
set -euo pipefail

pushd "${REPO_ROOT}" >/dev/null
python -m src prompt . > "${OUTPUT_DIR}/prompt.xml"
popd >/dev/null

echo "Repo-Prompt XML written to ${OUTPUT_DIR}/prompt.xml"
