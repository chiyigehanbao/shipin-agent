import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Application singletons are created during import, so test paths must be set here,
# before any test imports app.main or a repository.
_RUN_ID = f"pytest-{os.getpid()}-{uuid4().hex}"
_TEST_HUB = ROOT / "data" / _RUN_ID
_TEST_DB = ROOT / "data" / f"{_RUN_ID}.db"
_TEST_HUB.mkdir(parents=True, exist_ok=True)
(_TEST_HUB / "outputs" / "assets").mkdir(parents=True, exist_ok=True)
os.environ["MODELHUB_ROOT"] = str(_TEST_HUB)
os.environ["SQLITE_PATH"] = str(_TEST_DB)
