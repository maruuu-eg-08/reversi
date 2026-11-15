import random as rd


class RandomAI:
    def __init__(self, color):
        self.color = color

    def get_move(self, board):
        """打てる手の中からランダムに1つ選ぶ。打てる手がなければ None。"""
        valid_moves = board.listUp(self.color)
        if not valid_moves:
            return None
        return rd.choice(valid_moves)
