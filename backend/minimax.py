from bitboard import BitBoard as board
import random as rd

class MinimaxAI:
    def __init__(self, color, max_depth=4):
        self.color = color
        self.max_depth = max_depth
        # 重み表を1次元のリスト(64要素)にして計算を高速化
        self.weights = [
            30,-12, 0,-1,-1, 0,-12, 30,
            -12,-15,-3,-3,-3,-3,-15,-12,
            0, -3, 0,-1,-1, 0, -3,  0,
            -1, -3,-1,-1,-1,-1, -3, -1,
            -1, -3,-1,-1,-1,-1, -3, -1,
            0, -3, 0,-1,-1, 0, -3,  0,
            -12,-15,-3,-3,-3,-3,-15,-12,
            30,-12, 0,-1,-1, 0,-12, 30
        ]

    def get_move(self, board):
        valid_moves = board.listUp(self.color)
        if not valid_moves:
            return None

        best_score = -float("inf")
        best_moves = []

        for row, col in valid_moves:
            # 🌟 NumPyのコピーではなく、整数の値を保存するだけ（爆速）
            orig_black = board.black
            orig_white = board.white

            board.put_disc(row, col, self.color)
            score = self.minimax(board, self.max_depth - 1, False, self.color * -1)
            
            # 🌟 値を戻すだけで盤面復元
            board.black = orig_black
            board.white = orig_white

            if score > best_score:
                best_score = score
                best_moves = [(row, col)]
            elif score == best_score:
                best_moves.append((row, col))
        
        return rd.choice(best_moves)

    def minimax(self, board, depth, is_maximizing, current_color):
        if depth == 0:
            return self.evaluate(board)
            
        valid_moves = board.listUp(current_color)
        
        # パスまたは終局判定
        if not valid_moves:
            if not board.has_valid_move(current_color * -1):
                return self.evaluate(board)
            return self.minimax(board, depth, not is_maximizing, current_color * -1)

        if is_maximizing:
            max_eval = -float('inf')
            for r, c in valid_moves:
                orig_black, orig_white = board.black, board.white
                board.put_disc(r, c, current_color)
                score = self.minimax(board, depth - 1, False, current_color * -1)
                board.black, board.white = orig_black, orig_white
                max_eval = max(max_eval, score)
            return max_eval
        else:
            min_eval = float('inf')
            for r, c in valid_moves:
                orig_black, orig_white = board.black, board.white
                board.put_disc(r, c, current_color)
                score = self.minimax(board, depth - 1, True, current_color * -1)
                board.black, board.white = orig_black, orig_white
                min_eval = min(min_eval, score)
            return min_eval

    def evaluate(self, board):
        # 🌟 NumPyを一切使わずにビット演算とリスト参照でスコア計算
        score = 0
        black = board.black
        white = board.white
        
        # 各マスの石をチェックして重みを加算
        for i in range(64):
            mask = 1 << i
            if black & mask:
                score += self.weights[i]
            elif white & mask:
                score -= self.weights[i]
        
        # AIの色に合わせてスコアを返す
        return score if self.color == 1 else -score