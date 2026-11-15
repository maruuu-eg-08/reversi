from bitboard import BitBoard as board
import random as rd
class RandomAI :
    def __init__(self, color):
        self.color = color

    #main.pyから直接呼ばれる入り口。ここでは現在の盤面から「自分が打てるすべての有効手」をリストアップしてその中からランダムに選んで返す関数
    def get_move(self, board):
        valid_moves = board.listUp(self.color)
        move = rd.choice(valid_moves)

        return move