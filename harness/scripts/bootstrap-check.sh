#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

for script in harness/scripts/*.sh; do
  bash -n "$script"
done
python3 - <<'PYCODE'
from pathlib import Path

root = Path.cwd()
required = [root / 'AGENTS.md', root / 'harness' / 'README.md']
required.extend((root / 'harness' / 'policies').glob('*.md'))
required.extend((root / '.agents' / 'skills').glob('*/SKILL.md'))
if not required or any(not path.is_file() for path in required):
    raise SystemExit('ERROR: required harness files are missing')
for skill in (root / '.agents' / 'skills').glob('*/SKILL.md'):
    data = skill.read_text(encoding='utf-8')
    if not data.startswith('---\n') or '\nname:' not in data or '\ndescription:' not in data:
        raise SystemExit(f'ERROR: invalid skill frontmatter: {skill}')
print(f'Bootstrap validation complete: {len(required)} documents checked.')
PYCODE
