import random as rd


class RandomAI:
    def __init__(self, color):
        self.color = color

    def get_move(self, board):
        """Pick a random legal move, or None if there is none."""
        valid_moves = board.listUp(self.color)
        if not valid_moves:
            return None
        return rd.choice(valid_moves)
