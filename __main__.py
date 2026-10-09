import sys
import os

# Ensure repo root is on sys.path if invoked from parent directory
repo_root = os.path.dirname(os.path.abspath(__file__))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from chaosharness.cli import main

if __name__ == "__main__":
    sys.exit(main())
