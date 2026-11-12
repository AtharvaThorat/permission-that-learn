import sys
from pathlib import Path

# Lets tests import support.py; the repository root also has a `tests` package.
sys.path.insert(0, str(Path(__file__).parent))
