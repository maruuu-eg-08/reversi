from bitboard import BitBoard as board
import numpy as np
import random as rd
import copy as cp

class AlphaBetaAI:
    # 🌟 eval_coeffs=None を追加
    def __init__(self, color, max_depth=6, weights=None, eval_coeffs=None):
        self.color = color
        self.depth = max_depth
        self.weights = weights if weights is not None else [
            50.0, 17.29, 6.80, 11.31, 11.31, 6.80, 17.29, 50.0,
            17.29, 18.43, 38.49,-28.38,-28.38, 38.49, 18.43, 17.29,
             6.80, 38.49,-17.33,-11.03,-11.03,-17.33, 38.49,  6.80,
            11.31,-28.38,-11.03, 18.70, 18.70,-11.03,-28.38, 11.31,
            11.31,-28.38,-11.03, 18.70, 18.70,-11.03,-28.38, 11.31,
             6.80, 38.49,-17.33,-11.03,-11.03,-17.33, 38.49,  6.80,
            17.29, 18.43, 38.49,-28.38,-28.38, 38.49, 18.43, 17.29,
            50.0, 17.29,  6.80, 11.31, 11.31,  6.80, 17.29, 50.0
        ]
        
        # 🌟 GAから係数が渡されたらそれを使う。なければデフォルト値。
        # [序盤Pos, 序盤Mob, 序盤Disc, 中盤Pos, 中盤Mob, 中盤Disc, 終盤Pos, 終盤Mob, 終盤Disc]
        self.eval_coeffs = eval_coeffs if eval_coeffs is not None else [
            1.11265999,  0.73565285,  0.34340917,
            1.05687437,  0.65200396,  0.43294245,
            -0.0449974,   0.53306816,  1.0032734
        ]
        
        self.tt = {}
        self.opening_book = {}
        #self._build_opening_book() # 🌟 GA学習中は定石を使わない方が純粋な評価ができます（今回はコメントアウトを推奨）

    def _calc_weight_score(self, bitboard):
        score = 0
        tmp_board = bitboard
        while tmp_board:
            one_right = tmp_board & -tmp_board
            # 一番右の1が何ビット目か（bit_count()は3.10以降なので、3.9でも動くbit_length()を使う）
            pos = one_right.bit_length() - 1
            score += self.weights[pos]
            tmp_board ^= one_right
        return score
    
    def evaluate(self, board):
        my_board = board.black if self.color == 1 else board.white
        opp_board = board.white if self.color == 1 else board.black

        my_count = bin(my_board).count('1')
        opp_count = bin(opp_board).count('1')
        empty_count = 64 - my_count - opp_count

        my_score = self._calc_weight_score(my_board)
        opp_score = self._calc_weight_score(opp_board)
        position_score = my_score - opp_score

        my_mb = bin(board.get_legal_board(self.color)).count('1')
        opp_mb = bin(board.get_legal_board(self.color * -1)).count('1')
        mobility_score = my_mb - opp_mb
        
        disc_score = my_count - opp_count

        # 🌟 self.eval_coeffs の値を使って計算する
        if empty_count >= 45:
            return position_score * self.eval_coeffs[0] + mobility_score * self.eval_coeffs[1] + disc_score * self.eval_coeffs[2]
        elif empty_count >= 15:
            return position_score * self.eval_coeffs[3] + mobility_score * self.eval_coeffs[4] + disc_score * self.eval_coeffs[5]
        else:
            return position_score * self.eval_coeffs[6] + mobility_score * self.eval_coeffs[7] + disc_score * self.eval_coeffs[8]

    # (get_move と alphabeta は以前のまま変更なし)

    def get_move(self, board):
        # 🌟 まずは定石を知っているかチェック！
        board_state = (board.black, board.white)
        if board_state in self.opening_book:
            return self.opening_book[board_state] # 知っていれば1ミリ秒で即答！

        # 定石にない場合は自力で考える
        self.tt.clear() # 探索前にメモ帳を白紙に戻す
        
        valid_moves = board.listUp(self.color)
        alpha = -float('inf')
        beta = float('inf')
        max_val = -float('inf')
        best_move = None

        valid_moves.sort(key = lambda pos: self.weights[pos[0] * 8 + pos[1]], reverse = True)
        
        for r,c in valid_moves:
            orig_black = board.black
            orig_white = board.white

            board.put_disc(r, c, self.color)
            score = self.alphabeta(board, self.depth - 1, alpha, beta, False, self.color * -1)
            
            board.black = orig_black
            board.white = orig_white

            if score > max_val:
                max_val = score
                best_move = (r, c)

            alpha = max(alpha, max_val)

        return best_move

    def alphabeta(self, board, depth, alpha, beta, is_maximizing, current_color):
        # 🌟 メモ帳（置換表）の確認
        state_key = (board.black, board.white, current_color)
        original_alpha = alpha
        original_beta = beta
        if state_key in self.tt and self.tt[state_key]['depth'] >= depth:
            tt_entry = self.tt[state_key]
            if tt_entry['type'] == 'exact':
                return tt_entry['score']
            elif tt_entry['type'] == 'lower':
                alpha = max(alpha, tt_entry['score'])
            elif tt_entry['type'] == 'upper':
                beta = min(beta, tt_entry['score'])
            if alpha >= beta:
                return tt_entry['score']

        valid_moves = board.listUp(current_color)

        if depth == 0 or (not valid_moves and not board.has_valid_move(current_color * -1)):
            return self.evaluate(board)

        if not valid_moves:
            return self.alphabeta(board, depth, alpha, beta, not is_maximizing, current_color * -1)

        if is_maximizing:
            valid_moves.sort(key = lambda pos: self.weights[pos[0] * 8 + pos[1]], reverse = True)
            best_score = -float("inf")
            for r,c in valid_moves:
                orig_black = board.black
                orig_white = board.white

                board.put_disc(r,c, current_color)
                score = self.alphabeta(board, depth - 1, alpha, beta, False, current_color * -1)
                
                board.black = orig_black
                board.white = orig_white

                best_score = max(best_score, score)
                alpha = max(alpha, best_score)
                if alpha >= beta:
                    break
        else:
            valid_moves.sort(key = lambda pos: self.weights[pos[0] * 8 + pos[1]], reverse = True)
            best_score = float('inf')
            for r,c in valid_moves:
                orig_black = board.black
                orig_white = board.white

                board.put_disc(r, c, current_color)
                score = self.alphabeta(board, depth -1, alpha, beta, True, current_color * -1)
                
                board.black = orig_black
                board.white = orig_white

                best_score = min(best_score, score)
                beta = min(beta, best_score)
                if beta <= alpha:
                    break

        # 🌟 探索が終わったら、結果をメモ帳（置換表）に記録する
        if best_score <= original_alpha:
            tt_type = 'upper'
        elif best_score >= original_beta:
            tt_type = 'lower'
        else:
            tt_type = 'exact'
            
        self.tt[state_key] = {'score': best_score, 'depth': depth, 'type': tt_type}

        return best_score