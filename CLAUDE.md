# CLAUDE.md

このファイルは、新しいチャットでも Claude がこのプロジェクトの経緯・進め方・現在の状況を思い出せるようにするためのメモです。
**作業が進むたびに Claude が更新する**（ユーザーの許可は不要、とユーザーが決めている）。最後の「作業履歴」と「現在の状況」を必ず最新に保つこと。

## プロジェクト概要

リバーシ（オセロ）AI のポートフォリオ。ユーザーは「より高度で、改善の過程が数字で見えるポートフォリオ」を目指している。

- リポジトリ（公開）: https://github.com/maruuu-eg-08/reversi
- Web版（GitHub Pages）: https://maruuu-eg-08.github.io/reversi/ — main への push で `.github/workflows/pages.yml` が自動デプロイ
- 会話は日本語。ユーザーは専門家ではないので、専門用語はかみ砕いて説明する
- **ユーザーに質問するときは、メッセージの最後に番号つきの「質問一覧」にまとめ、それぞれにおすすめの答えを書く**

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
frontend/         TypeScript UI。Rust 版エンジンを WebAssembly にして Web Worker で実行（wasm-engine.ts）。
                  npm run build で Rust→wasm のビルドから dist/ まで作る。npm test は Node での動作確認
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
- フロント: `rustup target add wasm32-unknown-unknown`（済み）、`cd frontend && npm run build && npm test`。
  ローカル確認は `.claude/launch.json` の reversi-web（port 8765, dist を配信）

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
- Web版は Rust を WebAssembly にして動かす（#16〜）。wasm-bindgen は使わず素の `extern "C"` 関数。
  i64 は JS の BigInt で受け渡し、wasm から返る値は符号つきなので `BigInt.asUintN(64, x)` で直す。
  wasm32 では `std::time::Instant` が使えないので `clock.rs` で JS の `performance.now` を `env.now_ms` として読み込む
- Web版用に Rust へ移植した Lv.1〜4・読み筋（AlphaBeta）・定石・定石名は `tests/test_rust_web_port.py` で Python 版と一致を確認。
  Lv.2/3 はランダムに選ぶので「最高点の手の一覧」の一致を見る。対称な局面でも小数の足し算の順で同点にならないことがある
- auto mode では force push が拒否される。リベースしたブランチは新しい名前で push して PR を出す
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
| #12 | CLAUDE.md を追加 | |
| #13 | パターン評価 step 3: 重みの学習（Rust、前処理つき共役勾配法） | 20万局で学習136秒、中盤 R² 0.634（線形 0.227） |
| #14 | パターン評価 step 4: 探索に組み込み・採用 | **パターン vs 線形 194勝6敗（97.0%）**。Lv.5 は Rust があれば既定でパターン評価 |
| #15 | パターン評価 step 5: 定石をパターン評価で作り直し | 新旧比較 53.0%（有意差なし）だがユーザー判断でマージ。主手順が虎→Aubrey に一致 |
| #16 | Web版を Rust（WebAssembly）化、Pyodide を廃止 | wasm 145KB、ブラウザで1秒9〜10手読み（パターン評価）、Node のテストを CI に追加 |

## 現在の状況と次のステップ

パターン評価（#10〜#15）と Web版の WebAssembly 化（#16）まで完了。

- 学習データ `data/selfplay-200k.bin`（20万局、gitignore 済み）。重みは `backend/pattern_weights.bin`（λ=30、採用版だけコミット）
- Web版の Lv.5 は Rust（wasm）＋パターン評価＋定石。Lv.1〜4 も Rust 移植版（Python 版と同じ手）
- マージの任され方（この一連の作業）: 対戦で有意に強くなったもの・ブラウザで動作確認できたものは CI 合格後にマージしてよい

次の候補（ユーザーと相談して決める）:
- パターン評価を使った自己対戦でデータを作り直し、再学習（強くなるか arena で確認）
- パターン評価の差分計算による高速化（打った手で変わるパターンだけ更新）
- README の先頭に GIF・スクリーンショット
