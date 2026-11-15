import random as rd

from weights import WEIGHTED_AI_WEIGHTS


class WeightedAI:
    def __init__(self, color):
        self.color = color
        self.weights = WEIGHTED_AI_WEIGHTS

    def evaluate(self, board):
        # 🌟 NumPy（board.grid）を使わずに、整数のビット演算で計算
        score = 0
        black = board.black
        white = board.white
        
        for i in range(64):
            mask = 1 << i
            if black & mask:
                score += self.weights[i]
            elif white & mask:
                score -= self.weights[i]
        
        # 自分の色に合わせてスコアを返す
        return score if self.color == 1 else -score

    def get_move(self, board):
        max_eval = -float('inf')
        best_moves = []
        valid_moves = board.listUp(self.color)
        
        if not valid_moves:
            return None

        for r, c in valid_moves:
            # 🌟 numpy.copy() ではなく、数字を保存するだけ（爆速）
            orig_black = board.black
            orig_white = board.white
            
            board.put_disc(r, c, self.color)
            score = self.evaluate(board)
            
            # 🌟 代入して元に戻す（タイムトラベル完了）
            board.black = orig_black
            board.white = orig_white
            
            if score > max_eval:
                max_eval = score
                best_moves = [(r, c)]
            elif score == max_eval:
                best_moves.append((r, c))
                
        return rd.choice(best_moves)