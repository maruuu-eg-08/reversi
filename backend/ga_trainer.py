import numpy as np
import random as rd
from ai_manager import create_ai
from bitboard import BitBoard as Board

population_size = 30  # 🌟 計算量削減のため少し減らします
generations = 100
mutation_rate = 0.1
elite_count = 3

# 🌟 今回は盤面の重みは固定にするので、以前の最強重みを読み込む（または定義する）
best_weights_64 = np.array([
    27.87, 10.59, 27.35, 15.77, 15.77, 27.35, 10.59, 27.87,
    10.59,  4.51, 33.77,-25.49,-25.49, 33.77,  4.51, 10.59,
    27.35, 33.77,  0.61, -6.42, -6.42,  0.61, 33.77, 27.35,
    15.77,-25.49, -6.42, 25.08, 25.08, -6.42,-25.49, 15.77,
    15.77,-25.49, -6.42, 25.08, 25.08, -6.42,-25.49, 15.77,
    27.35, 33.77,  0.61, -6.42, -6.42,  0.61, 33.77, 27.35,
    10.59,  4.51, 33.77,-25.49,-25.49, 33.77,  4.51, 10.59,
    27.87, 10.59, 27.35, 15.77, 15.77, 27.35, 10.59, 27.87
])

# 🌟 初期集団の生成（今回は9つの係数）
def init_population():
    # ベースとなる手動設定の係数 [序盤P, 序盤M, 序盤D, 中盤P, 中盤M, 中盤D, 終盤P, 終盤M, 終盤D]
    base_coeffs = np.array([0.55, 0.50, -0.05, 0.90, 0.35, 0.20, 0.25, 0.05, 0.90])
    population_coeffs = []
    
    for _ in range(population_size):
        # 🌟 係数なので、変異の幅は小さく（-0.2 ～ +0.2）する
        individual = base_coeffs + np.random.uniform(-0.2, 0.2, 9)
        population_coeffs.append(individual)
    return population_coeffs

def get_fitness(population_coeffs):
    fitness_score = np.zeros(population_size)
    matches_per_individual = 5 # 🌟 1人あたり5試合

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
        
        child = np.zeros(9) # 🌟 9つの係数
        for i in range(9):
            child[i] = parent_a[i] if rd.random() < 0.5 else parent_b[i]
            
        for i in range(9):
            if rd.random() < mutation_rate:
                child[i] += np.random.uniform(-0.2, 0.2) # 🌟 変異幅を小さく
        
        # 🌟 係数が極端になりすぎないように制限（-5.0 ～ 5.0）
        child = np.clip(child, -5.0, 5.0)
        next_generation.append(child)

    return next_generation

def run_match(idx1, idx2, population_coeffs):
    c1 = population_coeffs[idx1]
    c2 = population_coeffs[idx2]
    
    # 🌟 重み(weights)は固定で渡し、係数(eval_coeffs)を対戦相手ごとに変える！
    # 高速化のため、学習中は Depth = 2 で十分です
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

# play_game と select_parent は以前のまま変更なし
def play_game(player_black, player_white):
    board = Board()
    current_color = 1
    while board.has_valid_move(1) or board.has_valid_move(-1):
        if not board.has_valid_move(current_color):
            current_color *= -1
            continue

        current_player = player_black if current_color == 1 else player_white
        move = current_player.get_move(board)
        # move が None でないことを確認
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

def select_parent(population_coeffs, fitness_score, k=5): # 🌟 kを少し減らして多様性を確保
    selection_ix = np.random.choice(len(fitness_score), k, replace=False)
    best_ix = selection_ix[np.argmax(fitness_score[selection_ix])]
    return population_coeffs[best_ix]


# === メイン処理 ===
population_coeffs = init_population()

for gen in range(generations):
    scores = get_fitness(population_coeffs)
    best_idx = np.argmax(scores)
    avg_score = np.mean(scores)
    max_score = scores[best_idx]
    
    print(f"第 {gen:2} 世代 | 最高: {max_score:6.2f} | 平均: {avg_score:6.2f}")
    
    # 最強の係数を表示して、AIがどう学習しているか観察する！
    best_c = population_coeffs[best_idx]
    print(f"  [序盤] Pos: {best_c[0]:.2f}, Mob: {best_c[1]:.2f}, Disc: {best_c[2]:.2f}")
    print(f"  [中盤] Pos: {best_c[3]:.2f}, Mob: {best_c[4]:.2f}, Disc: {best_c[5]:.2f}")
    print(f"  [終盤] Pos: {best_c[6]:.2f}, Mob: {best_c[7]:.2f}, Disc: {best_c[8]:.2f}")

    population_coeffs = evolve(population_coeffs, scores)

# 最終世代の保存
best_idx = np.argmax(scores)
best_final = population_coeffs[best_idx]
np.savetxt("best_eval_coeffs.txt", best_final)
print("\n=== 学習完了！最強の係数 ===")
print(best_final)