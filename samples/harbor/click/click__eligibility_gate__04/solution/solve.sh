#!/bin/bash
# Apply the reference solution (used by Harbor's oracle agent).
set -euo pipefail
cd /app
git -c safe.directory=/app apply --whitespace=nowarn /solution/solution.patch
