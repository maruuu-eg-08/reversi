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
    files = []
    for var in ("PY_MODULES", "PY_DATA"):
        block = re.search(rf"{var} = \[(.*?)\]", script, re.S).group(1)
        files += re.findall(r'"([\w.]+)"', block)
    assert "opening_book.txt" in files
    for name in files:
        shutil.copy(ROOT / "backend" / name, tmp_path / name)

    # 開始局面は必ず定石に載っているので、Lv.5 は読まずに定石の手を返すはず
    code = (
        "import sys, json; sys.path.insert(0, '.'); sys.modules['numpy'] = None; "
        "import web_api; s = json.loads(web_api.new_game()); "
        "r = json.loads(web_api.ai_move(s['black'], s['white'], 1, '5', 4, 0.05)); "
        "assert r['move'] in s['legal']; assert r['book'] is True, r; "
        "assert json.loads(web_api.opening('f5d6c3d3c4'))['name'] == '虎（Tiger）'"
    )
    result = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
