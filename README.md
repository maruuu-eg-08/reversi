# Reversi AI

[![CI](https://github.com/maruuu-eg-08/reversi/actions/workflows/ci.yml/badge.svg)](https://github.com/maruuu-eg-08/reversi/actions/workflows/ci.yml)

ビットボードで実装したリバーシ（オセロ）エンジンと、強さの異なる複数のAIです。

**▶ ブラウザで遊ぶ: https://maruuu-eg-08.github.io/reversi/**

Python のエンジンを [Pyodide](https://pyodide.org/) でブラウザ内実行しているので、サーバーなしで動きます。
あなたの番では、打てる各マスを AI が読んだ評価値をヒートマップで表示します（対局中にオン/オフ可能）。
「一手戻す」で待ったができ、棋譜は「f5d6c3…」形式でコピーできます。
序盤は Lv.5 が事前に解析した定石で即答し、打っている定石の名前（虎・牛・ローズなど）も表示します。

## 特徴

- **ビットボード盤面**：盤面を64ビット整数2つで表現し、シフト演算で合法手生成・石の反転を行う（perft テストと、素朴な実装との比較テストで正しさを確認）
- **段階的なAI**
  | Level | AI | 手法 |
  |---|---|---|
  | 1 | RandomAI | 合法手からランダム |
  | 2 | WeightedAI | マスごとの重み表で1手読み |
  | 3 | MinimaxAI | ミニマックス探索（深さ4） |
  | 4 | AlphaBetaAI | αβ探索＋置換表、位置・着手可能数・石数を局面の進行度で重み付け。終局局面は実際の勝敗で評価 |
  | 5 | StrongAI | 時間制限つき反復深化＋PVS、終盤は完全読み、序盤は定石。評価関数は自己対戦データから線形回帰で学習（下記） |
- **Rust 版エンジン**：探索・評価・合法手生成を Rust に移植し、PyO3 で Python から呼び出す（`backend_rust/`）。Python 版と探索局面数まで完全に一致したまま約80倍高速
- **序盤の定石（opening book）**：序盤の 7,122 局面を 10 手先まで事前に解析した表。盤面の8通りの対称性で局面をまとめて保存（`build_book.py`, `opening_book.py`）。生成は GitHub Actions + PyPy で実行
- **定石名の判定**：Robert Gatliff の定石リスト（77種）と照合し、どの向きから打っても「虎（Tiger）」などを判定（`openings.py`）
- **評価関数の学習**：自己対戦の棋譜から最小二乗法で係数を推定（`tune_eval.py`）。以前は遺伝的アルゴリズム（`ga_trainer.py`）
- **AI同士の対戦ベンチマーク**：先後入れ替え・並列実行・勝率の95%信頼区間つき（`arena.py`）
- **Web版**：Python エンジンを Web Worker 上の Pyodide で実行し、TypeScript の UI から呼び出す。AI の読み筋（全合法手の評価値）を可視化。待った（一手戻す）・棋譜の表示とコピーにも対応
- **pygame GUI** と **ターミナル版**

## 使い方

```bash
pip install -r requirements.txt
cd backend
python gui.py        # GUIで対戦
python main.py       # ターミナルで対戦
python arena.py lv5:0.3 lv4 -n 50   # Lv.5（1手0.3秒）と Lv.4 を 50 序盤×先後で100戦
python tune_eval.py --games 4000      # 自己対戦から評価関数を学習
python arena.py lv5:0.3 lv5:0.3:book=off -n 200   # 定石あり vs なし
python arena.py lv5:0.3 lv5:0.3:engine=python -n 100   # Rust 版 vs Python 版
python evaluate_book.py -n 400                      # 定石の手と0.3秒探索の手を比較
python build_book.py --depth 10 --full-plies 6 --plies 8   # 定石を生成（8コアで数時間）
```

### Rust 版エンジンを使う（任意）

Rust（1.87 以上）が入っていれば、次のコマンドで Python から使えるようになります。
入れると Lv.5・定石の生成・学習・対戦ツールが自動的に Rust 版で動きます（入れなければ Python 版のまま）。

```bash
pip install ./backend_rust          # または: cd backend_rust && maturin develop --release
cd backend_rust && cargo test --release
```

### Web版をローカルで動かす

```bash
cd frontend
npm install
npm run serve   # http://localhost:8000
```

### テスト・lint

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## ベンチマーク結果

`arena.py` で、ランダムに数手進めた同じ序盤から先手・後手を入れ替えて対戦（CPython, 8並列）。
定石より上の行の Lv.5 は、定石を導入する前に測定したものです（現在の Lv.5 は既定で定石を使い、`book=off` で無効化）。

| 対戦 | 対局数 | 勝-敗-分 | 勝率（95%信頼区間） | 平均石差 |
|---|---|---|---|---|
| Lv.5（1手0.3秒） vs Lv.4（深さ4） | 100 | 98-2-0 | 98.0%（95.3–100%） | +43.6 |
| Lv.5 学習後 vs 学習前（ともに0.3秒） | 100 | 87-13-0 | 87.0%（80.4–93.6%） | +35.3 |
| Lv.4 vs Lv.2 | 20 | 20-0-0 | – | +39.0 |
| Lv.5 定石あり vs なし（ともに0.3秒） | 400 | 202-185-13 | 52.1%（47.2–57.0%）有意差なし | +1.5 |
| Lv.5 Rust 版 vs Python 版（ともに0.3秒） | 200 | 193-7-0 | 96.5%（94.0–99.0%） | +40.2 |

### 評価関数の学習（`tune_eval.py`）

Lv.5 の評価関数は「位置の重み・着手可能数・石数・開放度」の4特徴量 × 序盤/中盤/終盤の線形和です。
自己対戦で集めた局面の特徴量から、その対局の最終石差を最小二乗法で予測するように係数を求めました。

| 反復 | 自己対戦に使った係数 | 中盤の R² | 前の係数との対戦（0.1秒/手, 200局） |
|---|---|---|---|
| 1 | 学習前 | 0.21 | 86.8%（82.1–91.4%） |
| 2 | 反復1の結果 | 0.32 | 76.0%（70.1–81.9%）← 採用 |
| 3 | 反復2の結果 | 0.31 | 54.8%（47.9–61.6%）有意差なし → 収束と判断 |

序盤は R² がほぼ 0（序盤の特徴量だけでは勝敗をほとんど説明できない）でした。序盤は探索の深さ（下記の定石）で補っています。

### 序盤の定石（`build_book.py`）

開始局面から6手目までに現れる**すべての局面**と、その先8手目までの「AI の最善手 × 相手の有力な上位3手」の局面を、
深さ10で読んだ最善手として登録しました（7,122局面、325KB）。

- **対称性**：盤面を回転・反転した8通りのうち最小のものを正規形として保存し、引くときに手を逆変換する。表の大きさが約1/8になり、どの向きから打たれても同じ定石を使える
- **再現性と再開**：時間制限ではなく固定の深さで読むので、同じ設定なら1文字も違わないファイルができる。読み終えた局面は随時ファイルに追記し、中断しても続きから再開できる（テストで確認）
- **計算環境**：最初は GitHub Actions（4コア）＋ PyPy で約2.5時間かかった。Rust 版エンジンでは手元の8コアで **2分12秒** になり、生成したファイルは元のものと1文字も違わなかった（`.github/workflows/build-book.yml` も既定で Rust 版を使う）

**効果の測定**

| 測定 | 結果 |
|---|---|
| 対局（上の表、ランダム6手の序盤から） | 52.1%（47.2–57.0%）。強くなったとは言えない |
| 同じ序盤局面400個で、0.3秒探索（平均6.1手読み）の手と定石の手を比較（`evaluate_book.py`） | 一致は26%。違う手の場合、深さ10の評価では平均 2.85 の損（評価値の単位はおおよそ石数） |

深く読むと選ぶ手は大きく変わるのに、勝率にはほとんど表れませんでした。
序盤の評価関数の精度が低い（R² ≈ 0）ため、深く読んでも「より良い手」にはなりにくいと考えられます。
現状の定石の主な利点は、序盤を読まずに即答できること（Web版では待ち時間がなくなる）です。
強さを伸ばすには、評価関数そのものの改善（辺・隅のパターン評価）が次の課題です。

### Rust 版エンジン（`backend_rust/`）

`strong_ai.py` の計算の重い部分（合法手生成・評価関数・反復深化 PVS 探索・置換表）だけを Rust に移植しました。
学習・定石の生成・対戦などのツールは Python のまま、`StrongAI` が自動的に Rust 版を呼び出します。
ブラウザ版（Pyodide）は Rust 版なしで Python 版のまま動きます。

**Python 版と同じ結果になることを保証**

固定の深さで読んだとき、最善手・評価値（浮動小数点数として完全一致）・**探索した局面数**まで Python 版と一致することを、
ランダムな局面と終盤の完全読みでテストしています（`tests/test_rust_engine.py`）。
局面数まで一致するので、手の並べ替え・置換表・枝刈りが同じ順番で動いていることになります。

移植中に、Python 3.12 から `sum()` が浮動小数点数を誤差補正つきで足すようになったため、
重み表の合計が Python のバージョンによって最後の桁だけ違うことが分かりました。
足す順番を明示したループに直し、Python 3.10〜3.13・PyPy・Rust のすべてで同じ値になるようにしています。

**速さ**（序盤の8局面、M シリーズ Mac・1コア）

| 深さ | Python 版 | Rust 版 | 倍率 |
|---|---|---|---|
| 8 | 1.50 秒/局面（13万局面/秒） | 0.018 秒/局面（1,091万局面/秒） | 約84倍 |
| 10 | 10.0 秒/局面（12万局面/秒） | 0.129 秒/局面（965万局面/秒） | 約78倍 |

同じ0.3秒でも Rust 版はより深く読めるため、Python 版に 96.5% 勝ちます（上のベンチマーク表）。

## ディレクトリ構成

```
backend/
  bitboard.py      盤面（ビットボード）
  weights.py       評価パラメータ（重み表・GA学習済み係数）
  *_ai.py          各レベルのAI
  strong_ai.py     Lv.5（反復深化・PVS・完全読み）
  opening_book.py  定石の表（対称性による正規化・保存・検索）
  build_book.py    定石の生成（並列・決定的・中断から再開可）
  opening_book.txt 生成した定石（7,122局面）
  openings.py      名前の付いた定石（77種）の判定
  evaluate_book.py 定石の手と短時間探索の手の比較
  tune_eval.py     自己対戦データから評価関数を学習
  arena.py         AI同士の並列対戦・勝率の信頼区間
  ga_trainer.py    遺伝的アルゴリズムによる係数学習（旧）
  ai_benchmark.py  AI同士の対戦ベンチマーク（旧）
  web_api.py       Web版から呼ぶ JSON API
  gui.py / main.py GUI版 / ターミナル版
backend_rust/      Rust 版エンジン（Python から import reversi_engine で使う）
  src/board.rs     合法手生成・石の反転
  src/eval.rs      評価関数
  src/search.rs    反復深化 PVS 探索・置換表
  src/lib.rs       Python バインディング（PyO3）
tests/             pytest（tests/test_rust_engine.py で Python 版との一致を確認）
frontend/
  src/app.ts       盤面UI・対局の進行
  src/worker.ts    Pyodide を読み込み Python エンジンを実行する Web Worker
  src/engine.ts    Worker との通信
```

## Web版の仕組み

```
ブラウザ（メインスレッド）            Web Worker
  app.ts  ── postMessage ──▶  worker.ts ── Pyodide(CPython) ──▶ backend/*.py
   盤面UI   ◀── JSON 結果 ───            web_api.py → alphabeta_ai.py など
```

## 今後の予定

- より表現力の高い評価関数（辺・隅のパターン）の学習
