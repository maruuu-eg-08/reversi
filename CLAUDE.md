# CLAUDE.md

このファイルは、新しいチャットでも Claude がこのプロジェクトの経緯・進め方・現在の状況を思い出せるようにするためのメモです。
**作業が進むたびに Claude が更新する**（ユーザーの許可は不要、とユーザーが決めている）。最後の「作業履歴」と「現在の状況」を必ず最新に保つこと。

## プロジェクト概要

リバーシ（オセロ）AI のポートフォリオ。ユーザーは「より高度で、改善の過程が数字で見えるポートフォリオ」を目指している。

- リポジトリ（公開）: https://github.com/maruuu-eg-08/reversi
- Web版（GitHub Pages）: https://maruuu-eg-08.github.io/reversi/ — main への push で `.github/workflows/pages.yml` が自動デプロイ
- 会話は日本語。ユーザーは専門家ではないので、専門用語はかみ砕いて説明する

## 構成

```
backend/          Python のエンジンとツール（Web版は Pyodide でこれをそのまま実行）
  bitboard.py       盤面（ビットボード）
  strong_ai.py      Lv.5（反復深化 PVS・置換表・終盤完全読み・定石）。Rust 版があれば自動で使う
  weights.py        評価パラメータ（STRONG_EVAL_COEFFS など）
  opening_book.py   定石の表（8対称の正規化）/ build_book.py 生成 / opening_book.txt 生成物（7,122局面）
  openings.py       定石名（Gatliff の77種）の判定
  patterns.py       パターン評価（Python 版）
  gen_data.py       自己対戦の学習データ生成（Rust 版が必要）
  arena.py          AI 同士の並列対戦（先後入れ替え・95%信頼区間・Elo）
  tune_eval.py      線形評価関数の学習 / evaluate_book.py 定石の効果測定
  web_api.py        Web版から呼ぶ JSON API
backend_rust/     Rust 版エンジン（PyO3、`import reversi_engine`）
  src/board.rs search.rs eval.rs pattern.rs selfplay.rs lib.rs
frontend/         TypeScript UI（Pyodide を Web Worker で実行）。npm run build で dist/
tests/            pytest（pythonpath = backend）
data/             学習データ（gitignore 済み、大きいのでコミットしない）
.github/workflows ci.yml（lint・test・rust・frontend）、pages.yml、build-book.yml（手動で定石生成）
```

## 開発環境とコマンド

- Python は anaconda の python3（3.13）。ruff はシステムに無いので仮想環境に入れて使う
- Rust 1.94（`~/.cargo/bin`）。Rust 版の Python 拡張は仮想環境に `maturin develop --release` で入れる。
  anaconda 環境では `env -u CONDA_PREFIX VIRTUAL_ENV=<venv> PATH=<venv>/bin:$PATH maturin develop --release` のように CONDA_PREFIX を外す必要がある
- これまではセッションの一時ディレクトリの venv を使っていた（消えることがある）。消えていたら作り直す:
  `python3 -m venv <dir> && <dir>/bin/pip install maturin pytest numpy ruff`
- テスト: Rust 入り venv で `pytest`（Rust 一致テストを含む）と、anaconda の `python3 -m pytest`（Rust なし＝ブラウザと同じ経路）の両方
- lint: `ruff check .`、`cd backend_rust && cargo fmt --check && cargo clippy --all-targets --features python -- -D warnings && cargo test --release`
- フロント: `cd frontend && npm run build`。ローカル確認は `.claude/launch.json` の reversi-web（port 8765, dist を配信）

## 進め方のルール（ユーザーと決めたこと）

- 作業は feature ブランチ → PR → CI 合格 → マージ。**マージと公開はユーザーの OK をもらってから**（一度だけ外出中に任された例外あり）
- コミットのメールは GitHub の noreply アドレス（リポジトリのローカル git config で設定済み）。個人のメールは出さない
- AI の強さの主張は `arena.py` の対戦（先後入れ替え・95%信頼区間）で裏付ける。強くなったと示せたものだけ採用が原則。
  有意差がなかった結果も README に正直に書く
- README のベンチマーク表を最新に保ち、デプロイ後は公開ページで動作確認する
- 長い計算は、始める前に所要時間の見込みを伝え、進捗を表示する（無言で長時間待たせない）
- 重い計算は Rust 版で手元（8コア）か、GitHub Actions（`build-book.yml` のように手動実行・キャッシュで再開）。
  AWS は将来の強化学習・深層学習で検討（まず無料の手段から）
- Python 版と Rust 版は**同じ結果**を保つ: 探索・評価を変えるときは両方を直し、`tests/test_rust_engine.py`（手・評価値・探索局面数まで一致）を通す

## 技術的な注意点（ハマったこと）

- Python 3.12 から `sum()` が浮動小数点を誤差補正つきで足すため、バージョンで最後の桁がずれた → 足す順番を明示したループにした
- パターン評価の重みは整数（1/64 石）にして、Python・Rust で足す順番によらず完全一致させている
- パターンのインスタンスは「マスと順番」が違う回転・反転をすべて含める（84個）→ どんな重みでも評価が盤面対称
- GitHub Pages は10分キャッシュ → ビルド時に全ファイルの URL に `?v=<hash>` を付けて新旧の混在を防いでいる
- Web版（Pyodide）には Rust 版が無い。ブラウザを速くするには Rust を WebAssembly 化する必要がある（未着手）
- PyO3 0.22 のマクロに clippy::useless_conversion が誤反応するので lib.rs の python モジュールで allow している
- 定石は勝率で有意差なし（52.1%）。序盤の線形評価関数の精度（R²≈0）が限界 → パターン評価に取り組む理由

## 作業履歴

### 2026-11-15〜16（最初の長いチャット）
| PR | 内容 | 主な結果 |
|---|---|---|
| #1 | バグ修正・GUI改善・テストとCI | perft で合法手生成を検証 |
| #2 | Web版（Pyodide＋TypeScript、読み筋の可視化） | GitHub Pages で公開 |
| #3 | Lv.5（反復深化・PVS・完全読み）＋線形評価関数の学習 | Lv.5 vs Lv.4 98%、学習後 vs 前 87% |
| #4 | 評価値の数字を対局中に表示/非表示（E キー） | |
| #5 | 一手戻す（⌘Z）と棋譜表示・コピー | |
| #6 | 公開直後に新旧ファイルが混ざる問題（URL にバージョン） | |
| #7 | 定石生成用の GitHub Actions ワークフロー | PyPy は CPython の約3.1倍速 |
| #8 | 序盤の定石（深さ10、7,122局面）と定石名の表示 | 定石あり vs なし 52.1%（有意差なし） |
| #9 | Rust 版エンジン（PyO3） | 約80倍速、Python と完全一致、同じ0.3秒で Rust 96.5% 勝ち、定石再生成 2.5時間→2分12秒（同一ファイル） |
| #10 | パターン評価 step 1: パターン定義（11種・84インスタンス・15段階・整数重み） | Rust/Python 一致、評価が厳密に対称 |
| #11 | パターン評価 step 2: 自己対戦の学習データ生成 | 約54局/秒、中断から再開可・決定的 |

## 現在の状況と次のステップ

パターン評価の計画（ユーザー承認済み、段階ごとに PR）:
1. ✅ パターンの定義と取り出し（#10）
2. ✅ 学習データ生成ツール（#11）。本番データ 20万局（約1,200万局面）を `data/selfplay-200k.bin` に生成中
   （設定: 序盤ランダム8〜20手、中盤は深さ6、空き14から読み切り、seed 0。ログは `data/gen-200k.log`。
   中断しても `python gen_data.py --games 200000 --batch 2000 --out ../data/selfplay-200k.bin` で再開できる）
3. ⏳ **次: 学習**。段階ごとに「パターン → 最終石差」の最小二乗（L2 正則化）を解く。予定は Rust で疎な共役勾配法、
   ゲーム単位で学習用/検証用に分けて精度（RMSE・R²）を線形評価と比較、最後に 1/64 単位の整数に丸めて保存
4. 評価関数をパターン評価に置き換え（Python・Rust 両方）、arena で現行と対戦して強くなったら採用
5. 新しい評価関数で定石を作り直す（Rust なら数分）
6. Web版への反映（重みファイルが数 MB・Python では遅いので、Web版の Rust/WebAssembly 化と一緒に）
