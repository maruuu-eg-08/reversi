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
    """Play level_a against level_b `trials` times, swapping colors for half of the games.

    Returns the disc differences from level_a's point of view (level_a discs - level_b discs).
    """
    print(f"Level {level_a} vs Level {level_b}: {trials} games (colors swapped)...")
    results = []

    for i in range(trials):
        if i % 2 == 0:
            a_score, b_score = play_game(level_a, level_b)  # A plays black (first)
        else:
            b_score, a_score = play_game(level_b, level_a)  # A plays white (second)
        results.append(a_score - b_score)
        if (i + 1) % 10 == 0:
            print(f"{i+1} games done...")

    results = np.array(results)
    wins = int(np.sum(results > 0))
    losses = int(np.sum(results < 0))
    draws = int(np.sum(results == 0))
    win_rate = (wins + 0.5 * draws) / trials * 100
    mean_diff = np.mean(results)
    std_diff = np.std(results)

    print(f"\n=== results (from Level {level_a}'s point of view) ===")
    print(f"wins: {wins} | losses: {losses} | draws: {draws}")
    print(f"win rate (draw = 0.5): {win_rate:.2f}%")
    print(f"mean disc difference: {mean_diff:.2f}")
    print(f"standard deviation: {std_diff:.2f}")

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
    parser = argparse.ArgumentParser(description="Compare two AIs by playing them against each other")
    parser.add_argument("level_a", nargs="?", default="4", help="level of the AI to evaluate (1-4)")
    parser.add_argument("level_b", nargs="?", default="2", help="level of the opponent (1-4)")
    parser.add_argument("-n", "--trials", type=int, default=100, help="number of games")
    parser.add_argument("--no-plot", action="store_true", help="do not show the histogram")
    args = parser.parse_args()
    run_benchmark(args.level_a, args.level_b, args.trials, show_plot=not args.no_plot)
