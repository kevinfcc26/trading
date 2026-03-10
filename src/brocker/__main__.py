import sys
import os

# Make src importable when running as: python -m brocker
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from entrypoints.cli.main import app

if __name__ == "__main__":
    app()
