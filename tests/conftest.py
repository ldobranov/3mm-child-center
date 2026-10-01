"""Make extension-owned service helpers importable in direct service tests."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "service"))
