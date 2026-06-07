#!/bin/bash
# Synthetic verifier stub. Mirrors the corpus contract: write the reward to
# /logs/verifier/reward.txt and the captured change to /logs/artifacts/model.patch.
set -uo pipefail
mkdir -p /logs/artifacts
echo "" > /logs/artifacts/model.patch
echo 1 > /logs/verifier/reward.txt
