import os
from pathlib import Path

# Get the path to the examples directory
PROJECT_ROOT = Path(__file__).parent
EXAMPLES_DIR = PROJECT_ROOT / "examples"

MIGRATION_SCRIPTS_DIR = os.getenv("MIGRATION_SCRIPTS_DIR", str(PROJECT_ROOT))
