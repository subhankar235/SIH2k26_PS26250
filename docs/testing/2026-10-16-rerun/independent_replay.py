"""Replay unchanged audit source with a neutral code filename.

This exposes application behavior coupled to audit_system.py stack-frame names.
Use --skip-browser for the 1,306 backend cases; omit it for the full 1,375 cases.
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
source = root / 'scripts/audit_system.py'
sys.path.insert(0, str(source.parent))
sys.argv = [str(source), '--output', 'docs/testing/2026-10-16-rerun/independent-replay', *sys.argv[1:]]
exec(compile(source.read_text(encoding='utf-8'), 'independent_replay.py', 'exec'),
     {'__file__':str(source), '__name__':'__main__'})
