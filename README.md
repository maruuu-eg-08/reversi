# Reversi AI

ビットボードで実装したリバーシ（オセロ）エンジンと、強さの異なる複数のAIです。

## 特徴

- **ビットボード盤面**：盤面を64ビット整数2つで表現し、シフト演算で合法手生成・石の反転を行う（perft で深さ7まで正しさを確認済み）
- **段階的なAI**
  | Level | AI | 手法 |
  |---|---|---|
  | 1 | RandomAI | 合法手からランダム |
  | 2 | WeightedAI | マスごとの重み表で1手読み |
  | 3 | MinimaxAI | ミニマックス探索（深さ4） |
  | 4 | AlphaBetaAI | αβ探索＋置換表、位置・着手可能数・石数を局面の進行度で重み付け |
- **遺伝的アルゴリズムによる評価関数の学習**（`ga_trainer.py`）
- **AI同士の対戦ベンチマーク**（`ai_benchmark.py`）
- **pygame GUI** と **ターミナル版**

## 使い方

```bash
pip install -r requirements.txt
cd backend
python gui.py        # GUIで対戦
python main.py       # ターミナルで対戦
python ai_benchmark.py
```

## ディレクトリ構成

```
backend/   Python製のエンジン・AI・GUI
frontend/  Web版（作成中）
```

## 今後の予定

- テスト（perft）とCIの整備
- 反復深化・終盤完全読みによるAI強化
- ブラウザで遊べるWeb版
