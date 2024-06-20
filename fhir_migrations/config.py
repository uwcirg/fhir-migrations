import os
from pathlib import Path

# Get the path to the examples directory
EXAMPLES_DIR = os.path.join(Path(__file__).parent, "examples")

MIGRATION_SCRIPTS_DIR = os.getenv("MIGRATION_SCRIPTS_DIR", str(EXAMPLES_DIR))
