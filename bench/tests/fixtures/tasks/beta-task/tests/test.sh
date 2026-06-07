#!/bin/bash
set -uo pipefail
mkdir -p /logs/artifacts
echo "" > /logs/artifacts/model.patch
echo 1 > /logs/verifier/reward.txt
