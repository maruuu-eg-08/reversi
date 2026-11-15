from weights import EVAL_COEFFS, POSITION_WEIGHTS, WIN_SCORE


class AlphaBetaAI:
    def __init__(self, color, max_depth=6, weights=None, eval_coeffs=None):
        self.color = color
        self.depth = max_depth
        # the learned coefficients assume POSITION_WEIGHTS, so both come from weights.py
        self.weights = list(weights) if weights is not None else POSITION_WEIGHTS
        # [opening pos, mob, disc, midgame pos, mob, disc, endgame pos, mob, disc]
        self.eval_coeffs = list(eval_coeffs) if eval_coeffs is not None else EVAL_COEFFS

        self.tt = {}  # transposition table
        self.nodes = 0  # nodes visited by the last search (shown in the web version)
        self.opening_book = {}

    def _calc_weight_score(self, bitboard):
        score = 0
        tmp_board = bitboard
        while tmp_board:
            one_right = tmp_board & -tmp_board
            score += self.weights[one_right.bit_length() - 1]
            tmp_board ^= one_right
        return score

    def final_score(self, board):
        """Score of a finished game: winning comes first, then a larger disc difference."""
        my_board = board.black if self.color == 1 else board.white
        opp_board = board.white if self.color == 1 else board.black
        diff = my_board.bit_count() - opp_board.bit_count()
        if diff > 0:
            return WIN_SCORE + diff
        if diff < 0:
            return -WIN_SCORE + diff
        return 0

    def evaluate(self, board):
        my_board = board.black if self.color == 1 else board.white
        opp_board = board.white if self.color == 1 else board.black

        my_count = my_board.bit_count()
        opp_count = opp_board.bit_count()
        empty_count = 64 - my_count - opp_count

        position_score = self._calc_weight_score(my_board) - self._calc_weight_score(opp_board)
        mobility_score = (
            board.get_legal_board(self.color).bit_count()
            - board.get_legal_board(-self.color).bit_count()
        )
        disc_score = my_count - opp_count

        if empty_count >= 45:
            c = self.eval_coeffs[0:3]
        elif empty_count >= 15:
            c = self.eval_coeffs[3:6]
        else:
            c = self.eval_coeffs[6:9]
        return position_score * c[0] + mobility_score * c[1] + disc_score * c[2]

    def _order(self, moves):
        moves.sort(key=lambda pos: self.weights[pos[0] * 8 + pos[1]], reverse=True)
        return moves

    def get_move(self, board):
        board_state = (board.black, board.white)
        if board_state in self.opening_book:
            return self.opening_book[board_state]

        self.tt.clear()
        self.nodes = 0

        valid_moves = board.listUp(self.color)
        if not valid_moves:
            return None

        alpha = -float('inf')
        beta = float('inf')
        max_val = -float('inf')
        best_move = valid_moves[0]

        for r, c in self._order(valid_moves):
            orig_black, orig_white = board.black, board.white
            board.put_disc(r, c, self.color)
            score = self.alphabeta(board, self.depth - 1, alpha, beta, False, -self.color)
            board.black, board.white = orig_black, orig_white

            if score > max_val:
                max_val = score
                best_move = (r, c)
            alpha = max(alpha, max_val)

        return best_move

    def analyze(self, board):
        """Return the score of every legal move (for the analysis view).

        get_move prunes everything except the best line, so other moves have no exact score.
        Here each move is searched with a full window to get exact scores for all of them.
        Returns [((row, col), score), ...] sorted from best to worst.
        """
        self.tt.clear()
        self.nodes = 0
        results = []
        for r, c in self._order(board.listUp(self.color)):
            orig_black, orig_white = board.black, board.white
            board.put_disc(r, c, self.color)
            score = self.alphabeta(board, self.depth - 1, -float('inf'), float('inf'), False, -self.color)
            board.black, board.white = orig_black, orig_white
            results.append(((r, c), score))
        results.sort(key=lambda item: item[1], reverse=True)
        return results

    def alphabeta(self, board, depth, alpha, beta, is_maximizing, current_color):
        self.nodes += 1
        state_key = (board.black, board.white, current_color)
        original_alpha = alpha
        original_beta = beta
        tt_entry = self.tt.get(state_key)
        if tt_entry is not None and tt_entry['depth'] >= depth:
            if tt_entry['type'] == 'exact':
                return tt_entry['score']
            elif tt_entry['type'] == 'lower':
                alpha = max(alpha, tt_entry['score'])
            elif tt_entry['type'] == 'upper':
                beta = min(beta, tt_entry['score'])
            if alpha >= beta:
                return tt_entry['score']

        valid_moves = board.listUp(current_color)

        if not valid_moves:
            if not board.has_valid_move(-current_color):
                # neither side can move: the game is over, so score the actual result
                return self.final_score(board)
            # pass
            return self.alphabeta(board, depth, alpha, beta, not is_maximizing, -current_color)

        if depth == 0:
            return self.evaluate(board)

        self._order(valid_moves)
        if is_maximizing:
            best_score = -float("inf")
            for r, c in valid_moves:
                orig_black, orig_white = board.black, board.white
                board.put_disc(r, c, current_color)
                score = self.alphabeta(board, depth - 1, alpha, beta, False, -current_color)
                board.black, board.white = orig_black, orig_white

                best_score = max(best_score, score)
                alpha = max(alpha, best_score)
                if alpha >= beta:
                    break
        else:
            best_score = float('inf')
            for r, c in valid_moves:
                orig_black, orig_white = board.black, board.white
                board.put_disc(r, c, current_color)
                score = self.alphabeta(board, depth - 1, alpha, beta, True, -current_color)
                board.black, board.white = orig_black, orig_white

                best_score = min(best_score, score)
                beta = min(beta, best_score)
                if beta <= alpha:
                    break

        if best_score <= original_alpha:
            tt_type = 'upper'
        elif best_score >= original_beta:
            tt_type = 'lower'
        else:
            tt_type = 'exact'
        self.tt[state_key] = {'score': best_score, 'depth': depth, 'type': tt_type}

        return best_score
