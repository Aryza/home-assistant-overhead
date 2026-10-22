import sys, types
from pathlib import Path

pkg = types.ModuleType("overhead_test")
pkg.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components/overhead")]
sys.modules.setdefault("overhead_test", pkg)
