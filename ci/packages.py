"""Public discovery contract used by companion tools."""
from pathlib import Path
import json, subprocess
binary = Path(__file__).resolve().parents[1] / 'gramide'
manifest = json.loads(subprocess.check_output([str(binary), 'languages'], text=True))
assert manifest['schema_version'] == 1
packages = manifest['packages']
assert {p['id'] for p in packages} == {'almide', 'go', 'rust'}
assert len({p['name'] for p in packages}) == len(packages)
extensions = [ext for p in packages for ext in p['extensions']]
assert len(set(extensions)) == len(extensions)
for package in packages:
    assert package['name'] == 'gramide-' + package['id']
    assert package['version'] and all(e.startswith('.') and len(e)>1 for e in package['extensions'])
    assert {'check', 'symbols'}.issubset(package['capabilities'])
print('Language package discovery contract passed')
