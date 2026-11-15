import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_web_bundle_contains_all_imported_modules(tmp_path):
    """Web版にコピーする Python モジュールだけで web_api が import できることを確認する。

    （numpy などブラウザに無いパッケージや、コピー漏れのモジュールに依存していないか）
    """
    script = (ROOT / "frontend" / "scripts" / "copy-assets.mjs").read_text()
    block = re.search(r"PY_MODULES = \[(.*?)\]", script, re.S).group(1)
    modules = re.findall(r'"([\w.]+\.py)"', block)
    for name in modules:
        shutil.copy(ROOT / "backend" / name, tmp_path / name)

    code = (
        "import sys, json; sys.path.insert(0, '.'); sys.modules['numpy'] = None; "
        "import web_api; s = json.loads(web_api.new_game()); "
        "r = json.loads(web_api.ai_move(s['black'], s['white'], 1, '5', 4, 0.05)); "
        "assert r['move'] in s['legal']"
    )
    result = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
