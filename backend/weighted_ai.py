import random as rd

from weights import WEIGHTED_AI_WEIGHTS


class WeightedAI:
    def __init__(self, color):
        self.color = color
        self.weights = WEIGHTED_AI_WEIGHTS

    def evaluate(self, board):
        # integer bit operations instead of NumPy (board.grid)
        score = 0
        black = board.black
        white = board.white
        
        for i in range(64):
            mask = 1 << i
            if black & mask:
                score += self.weights[i]
            elif white & mask:
                score -= self.weights[i]
        
        # from this AI's color's point of view
        return score if self.color == 1 else -score

    def get_move(self, board):
        max_eval = -float('inf')
        best_moves = []
        valid_moves = board.listUp(self.color)
        
        if not valid_moves:
            return None

        for r, c in valid_moves:
            # save the two integers instead of numpy.copy() (much faster)
            orig_black = board.black
            orig_white = board.white
            
            board.put_disc(r, c, self.color)
            score = self.evaluate(board)
            
            # restore the board
            board.black = orig_black
            board.white = orig_white
            
            if score > max_eval:
                max_eval = score
                best_moves = [(r, c)]
            elif score == max_eval:
                best_moves.append((r, c))
                
        return rd.choice(best_moves)