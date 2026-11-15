from bitboard import BitBoard as Board
import random as rd

class WeightedAI:
    def __init__(self, color):
        self.color = color
        # 重み表を1次元のリスト（64要素）にして高速化
        self.weights = [
            50.0, 17.29252071353563, 6.807158001740879, 11.31582191932327, 11.31582191932327, 6.807158001740879, 17.29252071353563, 50.0,
            17.29252071353563, 18.43177187025853, 38.490510429971685, -28.38326841401012, -28.38326841401012, 38.490510429971685, 18.43177187025853, 17.29252071353563,
            6.807158001740879, 38.490510429971685, -17.33032482356527, -11.034756452813014, -11.034756452813014, -17.33032482356527, 38.490510429971685, 6.807158001740879,
            11.31582191932327, -28.38326841401012, -11.034756452813014, 18.704633593152508, 18.704633593152508, -11.034756452813014, -28.38326841401012, 11.31582191932327,
            11.31582191932327, -28.38326841401012, -11.034756452813014, 18.704633593152508, 18.704633593152508, -11.034756452813014, -28.38326841401012, 11.31582191932327,
            6.807158001740879, 38.490510429971685, -17.33032482356527, -11.034756452813014, -11.034756452813014, -17.33032482356527, 38.490510429971685, 6.807158001740879,
            17.29252071353563, 18.43177187025853, 38.490510429971685, -28.38326841401012, -28.38326841401012, 38.490510429971685, 18.43177187025853, 17.29252071353563,
            50.0, 17.29252071353563, 6.807158001740879, 11.31582191932327, 11.31582191932327, 6.807158001740879, 17.29252071353563, 50.0
        ]

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