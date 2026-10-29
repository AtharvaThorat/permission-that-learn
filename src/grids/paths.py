"""Source checkout assets and installed package resources have distinct roots."""
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[1]
