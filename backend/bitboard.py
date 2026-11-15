import numpy as np

MASK_LEFT_RIGHT = 0x7e7e7e7e7e7e7e7e

MASK_TOP_BOTTOM = 0x00ffffffffffff00

MASK_ALL_EDGES = 0x007e7e7e7e7e7e00

class BitBoard:
    def __init__(self):
        #配列ではなく、ただの数字
        self.black = 0#黒石の配置 初期は９
        self.white = 0#白石の配置 初期は0

        self._put_initial_disc(3,3,-1)
        self._put_initial_disc(4,4,-1)
        self._put_initial_disc(3,4,1)
        self._put_initial_disc(4,3,1)

    def _put_initial_disc(self, row, col, color):
        #座標を通し番号に変換
        position = row * 8 + col
        #おきたい座標の番号の回数だけ左にシフトする
        bit_mask = 1 << position

        #おきたい色の二進数列に自分の番号のところに１を立てる
        if color == 1:
            self.black |= bit_mask
        else:
            self.white |= bit_mask
    def get_flip_mask(self, row, col, color):
        # 1. 置いた場所を64ビットの数字（1が一つだけある状態）にする
        pos = row * 8 + col
        put_mask = 1 << pos

        # すでに石がある場所には絶対に置けない
        if (self.black | self.white) & put_mask:
            return 0 # ひっくり返せる石は「ゼロ（0）」

        # 自分と相手の盤面をセット
        my_board = self.black if color == 1 else self.white
        opp_board = self.white if color == 1 else self.black

        flipped_all = 0 # 最終的にひっくり返す石の軌跡を全部まとめる箱

        # 🌟 8方向のビームの設定 (シフト量, ワープ防止マスク)
        # 右(+1), 左(-1), 下(+8), 上(-8), 右下(+9), 左上(-9), 左下(+7), 右上(-7)
        directions = [
            (1, 0xfefefefefefefefe),   # 右 (列0へのワープを防止)
            (-1, 0x7f7f7f7f7f7f7f7f),  # 左 (列7へのワープを防止)
            (8, 0xffffffffffffffff),   # 下 (ワープしないので全部1)
            (-8, 0xffffffffffffffff),  # 上
            (9, 0xfefefefefefefefe),   # 右下
            (-9, 0x7f7f7f7f7f7f7f7f),  # 左上
            (7, 0x7f7f7f7f7f7f7f7f),   # 左下
            (-7, 0xfefefefefefefefe)   # 右上
        ]

        # 8方向にビームを発射！
        for shift, mask in directions:
            current_flip = 0
            
            # ビームの先端を1マス進める
            if shift > 0:
                ray = (put_mask << shift) & mask
            else:
                ray = (put_mask >> abs(shift)) & mask

            # 相手の石がある限り、ビームを奥へ奥へ進める！
            while (ray & opp_board) != 0:
                current_flip |= ray # 通過した相手の石を記録
                if shift > 0:
                    ray = (ray << shift) & mask
                else:
                    ray = (ray >> abs(shift)) & mask

            # 最後にビームの先端が「自分の石」に当たったら、挟み込み成功！
            if (ray & my_board) != 0:
                flipped_all |= current_flip # 記録した軌跡を「確定」に追加

        return flipped_all # 確定した「ひっくり返す石の位置」を返す

    def put_disc(self, row, col, color):
        # さっきのビーム関数を使って、ひっくり返せる石の場所(64ビットの数字)をもらう
        flip_mask = self.get_flip_mask(row, col, color)
        
        # 1個もひっくり返せないなら、そこには置けない（False）
        if flip_mask == 0:
            return False

        # 置く場所の数字を作る
        pos = row * 8 + col
        put_mask = 1 << pos

        # 🌟 ここが最大の魔法！「XOR（排他的論理和：^）」で一瞬で色を変える！
        if color == 1:
            self.black |= put_mask      # 1. 自分の石を置く
            self.black ^= flip_mask     # 2. 相手だった石を黒に変える
            self.white ^= flip_mask     # 3. 白の盤面から、ひっくり返された石を消滅させる
        else:
            self.white |= put_mask
            self.white ^= flip_mask
            self.black ^= flip_mask

        return True
    
    def listUp(self, color):
        """
        AIやGUIから「どこに打てる？」と聞かれた時に、
        打てる場所のリスト [(row, col), (row, col)...] を返す関数
        """
        
        
        # 64マス全部を調べますが、get_flip_maskが爆速なので一瞬で終わります！
        legal = self.get_legal_board(color)
        moves = []
        if legal == 0: return moves
        
        for i in range(64):
            if (legal >> i) & 1:
                moves.append((i // 8, i % 8))
        
        return moves

    def count_discs(self, color):
        """
        石の数を数える関数（Python 3.10未満対応版）
        """
        if color == 1:
            # bin()で2進数文字列にして、その中の "1" の数を数える
            return bin(self.black).count('1')
        else:
            return bin(self.white).count('1')
        
    def has_valid_move(self, color):
        """
        AIがパス判定をするための関数。
        打てる場所のリスト(listUp)の中身が1個以上あるか（True/False）を返します。
        """
        return self.get_legal_board(color) != 0
    
    def get_legal_board(self, color):
        my_board = self.black if color == 1 else self.white
        opp_board = self.white if color == 1 else self.black
        empty = ~(self.black | self.white)
        
        legal = 0
        direction =[
            (1, 0xfefefefefefefefe), (-1, 0x7f7f7f7f7f7f7f7f), # 左右
            (8, 0xffffffffffffffff), (-8, 0xffffffffffffffff), # 上下
            (7, 0x7f7f7f7f7f7f7f7f), (9, 0xfefefefefefefefe),  # 斜め
            (-7, 0xfefefefefefefefe), (-9, 0x7f7f7f7f7f7f7f7f) # 斜め
        ]
        for shift, mask in direction:
            if shift > 0:
                tmp = (my_board << shift) & opp_board & mask
            else:
                tmp = (my_board >> abs(shift)) & opp_board &mask
            if tmp == 0: continue
            for _ in range(5):
                if shift > 0:
                    tmp |= (tmp << shift) & opp_board & mask
                else:
                    tmp |= (tmp >> abs(shift)) & opp_board & mask
            if shift > 0:
                legal |= (tmp << shift) & empty & mask
            else:
                legal |= (tmp >> abs(shift)) & empty & mask
        return legal

# 🌟 @property をつけることで、gui.py 側は今まで通り board.grid として読み取れます！
    @property
    def grid(self):
        """
        GUIの描画用に、64ビットの整数を 8x8 のNumPy配列に変換して返す翻訳機
        """
        import numpy as np # (ファイルの一番上でimportしていればここは不要です)
        grid_array = np.zeros((8, 8), dtype=int)

        for row in range(8):
            for col in range(8):
                # マスの通し番号から、判定用のビット（1の場所）を作る
                pos = 1 << (row * 8 + col)

                # AND演算（&）で、そこに黒石か白石があるかチェック！
                if self.black & pos:
                    grid_array[row, col] = 1
                elif self.white & pos:
                    grid_array[row, col] = -1

        return grid_array

    # ターミナル版（main.py）用：今の盤面を表示する関数
    def display(self):
        grid = self.grid
        print("    a     b     c     d     e     f     g     h")
        for i in range(8):
            print(i + 1, end="   ")
            for j in range(8):
                if grid[i][j] == 0:
                    print("・", end="    ")
                elif grid[i][j] == 1:
                    print("●", end="     ")
                else:
                    print("○", end="     ")
            print("\n")
