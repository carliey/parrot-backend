"""Publish the backend's lesson content into the mobile bundle (or check parity)."""
import argparse
from pathlib import Path

root = Path(__file__).resolve().parent
source = root / 'app/lesson_plans.json'
target = root.parent / 'parrot-mobile/src/data/lesson-plans.json'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true')
args = parser.parse_args()
if args.check:
    if not target.exists() or source.read_bytes() != target.read_bytes():
        raise SystemExit('Mobile lesson content is out of date. Run python sync_lessons.py.')
    print('Backend and mobile lesson content match.')
else:
    target.write_bytes(source.read_bytes())
    print('Updated mobile lesson content.')
