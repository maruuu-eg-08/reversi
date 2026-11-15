import numpy as np
import matplotlib.pyplot as plt
from bitboard import BitBoard as Board
from ai_manager import create_ai

def play_game(level_black, level_white):
    board = Board()
    player_black = create_ai(level_black, 1)
    player_white = create_ai(level_white, -1)

    current_color = 1

    while board.has_valid_move(1) or board.has_valid_move(-1):
        if not board.has_valid_move(current_color):
            current_color *= -1
            continue

        current_player = player_black if current_color == 1 else player_white
        move = current_player.get_move(board)
        board.put_disc(move[0], move[1], current_color)
        current_color *= -1

    black_count = board.count_discs(1)
    white_count = board.count_discs(-1)

    return black_count, white_count

def run_benchmark(level_b, level_w, trials=100):
    print(f"Level {level_b}(黒) vs Level {level_w}(白) を {trials}回対戦させます...")
    results = []

    for i in range(trials):
        b_score, w_score = play_game(level_b, level_w)
        results.append(b_score - w_score) # 点数差を記録
        if (i + 1) % 10 == 0:
            print(f"{i+1}試合完了...")

    # 統計計算
    results = np.array(results)
    win_black = np.sum(results > 0)
    win_white = np.sum(results < 0)
    draws = np.sum(results == 0)

    win_rate = (win_black / trials) * 100
    mean_diff = np.mean(results)
    std_diff = np.std(results)

    print("\n=== 統計結果 ===")
    print(f"黒の勝数: {win_black} | 白の勝数: {win_white} | 引き分け: {draws}")
    print(f"黒の勝率: {win_rate:.2f}%")
    print(f"平均点数差 (黒-白): {mean_diff:.2f}点")
    print(f"標準偏差 (ばらつき): {std_diff:.2f}")

    # ヒストグラムの表示（点数差の分布）
    plt.hist(results, bins=20, color='skyblue', edgecolor='black')
    plt.axvline(mean_diff, color='red', linestyle='dashed', linewidth=1, label=f'Mean: {mean_diff:.2f}')
    plt.title(f"Score Difference Distribution (Level {level_b} vs {level_w})")
    plt.xlabel("Black Score - White Score")
    plt.ylabel("Frequency")
    plt.legend()
    plt.show()

if __name__ == "__main__":
    # レベル4(AlphaBeta) vs レベル2(Weighted) で100回テスト
    # ※AlphaBetaの深さが深いと時間がかかるので、まずは100回程度がおすすめ
    run_benchmark(level_b="1", level_w="4", trials=100)
