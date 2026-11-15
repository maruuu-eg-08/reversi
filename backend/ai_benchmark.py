import argparse

import numpy as np

from ai_manager import create_ai
from bitboard import BitBoard as Board


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

    return board.count_discs(1), board.count_discs(-1)


def run_benchmark(level_a, level_b, trials=100, show_plot=True):
    """level_a と level_b を、先手・後手を半分ずつ入れ替えて trials 回対戦させる。

    戻り値は level_a から見た石差（level_a の石数 - level_b の石数）の配列。
    """
    print(f"Level {level_a} vs Level {level_b} を {trials}回（先後入れ替え）対戦させます...")
    results = []

    for i in range(trials):
        if i % 2 == 0:
            a_score, b_score = play_game(level_a, level_b)  # A が黒（先手）
        else:
            b_score, a_score = play_game(level_b, level_a)  # A が白（後手）
        results.append(a_score - b_score)
        if (i + 1) % 10 == 0:
            print(f"{i+1}試合完了...")

    results = np.array(results)
    wins = int(np.sum(results > 0))
    losses = int(np.sum(results < 0))
    draws = int(np.sum(results == 0))
    win_rate = (wins + 0.5 * draws) / trials * 100
    mean_diff = np.mean(results)
    std_diff = np.std(results)

    print(f"\n=== 統計結果（Level {level_a} 視点）===")
    print(f"勝ち: {wins} | 負け: {losses} | 引き分け: {draws}")
    print(f"勝率（引き分けは0.5勝）: {win_rate:.2f}%")
    print(f"平均石差: {mean_diff:.2f}")
    print(f"標準偏差: {std_diff:.2f}")

    if show_plot:
        import matplotlib.pyplot as plt

        plt.hist(results, bins=20, color='skyblue', edgecolor='black')
        plt.axvline(mean_diff, color='red', linestyle='dashed', linewidth=1, label=f'Mean: {mean_diff:.2f}')
        plt.title(f"Disc Difference Distribution (Level {level_a} vs {level_b})")
        plt.xlabel(f"Level {level_a} discs - Level {level_b} discs")
        plt.ylabel("Frequency")
        plt.legend()
        plt.show()

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI同士を対戦させて強さを比較する")
    parser.add_argument("level_a", nargs="?", default="4", help="比較するAIのレベル (1-4)")
    parser.add_argument("level_b", nargs="?", default="2", help="対戦相手のレベル (1-4)")
    parser.add_argument("-n", "--trials", type=int, default=100, help="対戦数")
    parser.add_argument("--no-plot", action="store_true", help="ヒストグラムを表示しない")
    args = parser.parse_args()
    run_benchmark(args.level_a, args.level_b, args.trials, show_plot=not args.no_plot)
