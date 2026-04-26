"""Test bootstrap.

Pytest may be executed from different working directories in Colab, local shell,
or an extracted zip folder.  This file makes the project root importable so
`from src...` works consistently without requiring package installation first.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
