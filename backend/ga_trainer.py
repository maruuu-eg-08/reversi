import random as rd
from pathlib import Path

import numpy as np

from ai_manager import create_ai
from bitboard import BitBoard as Board
from weights import POSITION_WEIGHTS

population_size = 30  # kept small to limit computation
generations = 100
mutation_rate = 0.1
elite_count = 3

# The board weights stay fixed (POSITION_WEIGHTS in weights.py); only the evaluation coefficients are learned
best_weights_64 = np.array(POSITION_WEIGHTS)

# Initial population (9 coefficients)
def init_population():
    # hand-tuned base [opening P, M, D, midgame P, M, D, endgame P, M, D]
    base_coeffs = np.array([0.55, 0.50, -0.05, 0.90, 0.35, 0.20, 0.25, 0.05, 0.90])
    population_coeffs = []
    
    for _ in range(population_size):
        # coefficients, so mutations stay small (-0.2 to +0.2)
        individual = base_coeffs + np.random.uniform(-0.2, 0.2, 9)
        population_coeffs.append(individual)
    return population_coeffs

def get_fitness(population_coeffs):
    fitness_score = np.zeros(population_size)
    matches_per_individual = 5 # 5 games per individual

    for i in range(population_size):
        opponents = np.random.choice(
            [idx for idx in range(population_size) if idx != i],
            matches_per_individual,
            replace=False
        )
        for j in opponents:
            score_i, score_j = run_match(i, j, population_coeffs)
            fitness_score[i] += score_i
    return fitness_score

def evolve(population_coeffs, fitness_score):
    next_generation = []
    sorted_indices = sorted(range(len(fitness_score)), key=lambda i: fitness_score[i], reverse=True)
    
    for i in range(elite_count):
        elite_index = sorted_indices[i]
        next_generation.append(np.copy(population_coeffs[elite_index]))

    while len(next_generation) < population_size:
        parent_a = select_parent(population_coeffs, fitness_score)
        parent_b = select_parent(population_coeffs, fitness_score)
        
        child = np.zeros(9) # 9 coefficients
        for i in range(9):
            child[i] = parent_a[i] if rd.random() < 0.5 else parent_b[i]
            
        for i in range(9):
            if rd.random() < mutation_rate:
                child[i] += np.random.uniform(-0.2, 0.2) # small mutation
        
        # clamp coefficients to -5.0..5.0
        child = np.clip(child, -5.0, 5.0)
        next_generation.append(child)

    return next_generation

def run_match(idx1, idx2, population_coeffs):
    c1 = population_coeffs[idx1]
    c2 = population_coeffs[idx2]
    
    # fixed weights, coefficients differ per player
    # depth 2 is enough during training and keeps it fast
    ai1_black = create_ai("4", 1, weights=best_weights_64, eval_coeffs=c1)
    ai1_black.depth = 2 
    ai2_white = create_ai("4", -1, weights=best_weights_64, eval_coeffs=c2)
    ai2_white.depth = 2
    s1_b, s2_w = play_game(ai1_black, ai2_white)

    ai2_black = create_ai("4", 1, weights=best_weights_64, eval_coeffs=c2)
    ai2_black.depth = 2
    ai1_white = create_ai("4", -1, weights=best_weights_64, eval_coeffs=c1)
    ai1_white.depth = 2
    s2_b, s1_w = play_game(ai2_black, ai1_white)

    return s1_b + s1_w, s2_b + s2_w

# play_game and select_parent are unchanged
def play_game(player_black, player_white):
    board = Board()
    current_color = 1
    while board.has_valid_move(1) or board.has_valid_move(-1):
        if not board.has_valid_move(current_color):
            current_color *= -1
            continue

        current_player = player_black if current_color == 1 else player_white
        move = current_player.get_move(board)
        # make sure move is not None
        if move is not None:
            board.put_disc(move[0], move[1], current_color)
        current_color *= -1

    black_count = board.count_discs(1)
    white_count = board.count_discs(-1)
    play_score = black_count - white_count
    
    if play_score > 0:
        black_score = 3 + (play_score / 100)
        white_score = (play_score / 100) * -1
    elif play_score < 0:
        black_score = play_score / 100
        white_score = (play_score / 100) * -1 + 3
    else:
        black_score, white_score = 1, 1
    return black_score, white_score

def select_parent(population_coeffs, fitness_score, k=5): # smaller k keeps more diversity
    selection_ix = np.random.choice(len(fitness_score), k, replace=False)
    best_ix = selection_ix[np.argmax(fitness_score[selection_ix])]
    return population_coeffs[best_ix]


def main():
    population_coeffs = init_population()

    for gen in range(generations):
        scores = get_fitness(population_coeffs)
        best_idx = np.argmax(scores)
        avg_score = np.mean(scores)
        max_score = scores[best_idx]

        print(f"generation {gen:2} | best: {max_score:6.2f} | mean: {avg_score:6.2f}")

        # show the best coefficients to watch the learning
        best_c = population_coeffs[best_idx]
        print(f"  [opening] Pos: {best_c[0]:.2f}, Mob: {best_c[1]:.2f}, Disc: {best_c[2]:.2f}")
        print(f"  [midgame] Pos: {best_c[3]:.2f}, Mob: {best_c[4]:.2f}, Disc: {best_c[5]:.2f}")
        print(f"  [endgame] Pos: {best_c[6]:.2f}, Mob: {best_c[7]:.2f}, Disc: {best_c[8]:.2f}")

        population_coeffs = evolve(population_coeffs, scores)

    # Save the result.
    # Note: evolve() already ran at the end of the loop, so scores and population_coeffs belong to
    # different generations; save best_c, the best individual of the last evaluated generation.
    best_final = best_c
    out_path = Path(__file__).with_name("best_eval_coeffs.txt")
    np.savetxt(out_path, best_final)
    print(f"saved to {out_path}")
    print("\n=== training finished: best coefficients ===")
    print(best_final)


if __name__ == "__main__":
    main()
