# Reversi AI

[![CI](https://github.com/maruuu-eg-08/reversi/actions/workflows/ci.yml/badge.svg)](https://github.com/maruuu-eg-08/reversi/actions/workflows/ci.yml)

ビットボードで実装したリバーシ（オセロ）エンジンと、強さの異なる複数のAIです。

**▶ ブラウザで遊ぶ: https://maruuu-eg-08.github.io/reversi/**

Python のエンジンを [Pyodide](https://pyodide.org/) でブラウザ内実行しているので、サーバーなしで動きます。
あなたの番では、打てる各マスを AI が読んだ評価値をヒートマップで表示します。

## 特徴

- **ビットボード盤面**：盤面を64ビット整数2つで表現し、シフト演算で合法手生成・石の反転を行う（perft テストと、素朴な実装との比較テストで正しさを確認）
- **段階的なAI**
  | Level | AI | 手法 |
  |---|---|---|
  | 1 | RandomAI | 合法手からランダム |
  | 2 | WeightedAI | マスごとの重み表で1手読み |
  | 3 | MinimaxAI | ミニマックス探索（深さ4） |
  | 4 | AlphaBetaAI | αβ探索＋置換表、位置・着手可能数・石数を局面の進行度で重み付け。終局局面は実際の勝敗で評価 |
  | 5 | StrongAI | 時間制限つき反復深化＋PVS、終盤は完全読み。評価関数は自己対戦データから線形回帰で学習（下記） |
- **評価関数の学習**：自己対戦の棋譜から最小二乗法で係数を推定（`tune_eval.py`）。以前は遺伝的アルゴリズム（`ga_trainer.py`）
- **AI同士の対戦ベンチマーク**：先後入れ替え・並列実行・勝率の95%信頼区間つき（`arena.py`）
- **Web版**：Python エンジンを Web Worker 上の Pyodide で実行し、TypeScript の UI から呼び出す。AI の読み筋（全合法手の評価値）を可視化
- **pygame GUI** と **ターミナル版**

## 使い方

```bash
pip install -r requirements.txt
cd backend
python gui.py        # GUIで対戦
python main.py       # ターミナルで対戦
python arena.py lv5:0.3 lv4 -n 50   # Lv.5（1手0.3秒）と Lv.4 を 50 序盤×先後で100戦
python tune_eval.py --games 4000      # 自己対戦から評価関数を学習
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

| 対戦 | 対局数 | 勝-敗-分 | 平均石差 |
|---|---|---|---|
| Level 4 vs Level 2 | 20（先後入れ替え） | 20-0-0 | +39.0 |

## ディレクトリ構成

```
backend/
  bitboard.py      盤面（ビットボード）
  weights.py       評価パラメータ（重み表・GA学習済み係数）
  *_ai.py          各レベルのAI
  strong_ai.py     Lv.5（反復深化・PVS・完全読み）
  tune_eval.py     自己対戦データから評価関数を学習
  arena.py         AI同士の並列対戦・勝率の信頼区間
  ga_trainer.py    遺伝的アルゴリズムによる係数学習（旧）
  ai_benchmark.py  AI同士の対戦ベンチマーク（旧）
  web_api.py       Web版から呼ぶ JSON API
  gui.py / main.py GUI版 / ターミナル版
tests/             pytest
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

- 定石（序盤の手）を事前計算した opening book
- より表現力の高い評価関数（辺・隅のパターン）の学習
