MASK_LEFT_RIGHT = 0x7e7e7e7e7e7e7e7e

MASK_TOP_BOTTOM = 0x00ffffffffffff00

MASK_ALL_EDGES = 0x007e7e7e7e7e7e00

class BitBoard:
    def __init__(self):
        # plain integers instead of arrays
        self.black = 0# black discs
        self.white = 0# white discs

        self._put_initial_disc(3,3,-1)
        self._put_initial_disc(4,4,-1)
        self._put_initial_disc(3,4,1)
        self._put_initial_disc(4,3,1)

    def _put_initial_disc(self, row, col, color):
        # convert (row, col) to a square index
        position = row * 8 + col
        # shift left by the square index
        bit_mask = 1 << position

        # set that bit on the given color's board
        if color == 1:
            self.black |= bit_mask
        else:
            self.white |= bit_mask
    def get_flip_mask(self, row, col, color):
        # 1. the square as a 64-bit mask with a single bit set
        pos = row * 8 + col
        put_mask = 1 << pos

        # an occupied square can never be played
        if (self.black | self.white) & put_mask:
            return 0 # nothing can be flipped

        # player and opponent boards
        my_board = self.black if color == 1 else self.white
        opp_board = self.white if color == 1 else self.black

        flipped_all = 0 # accumulates every disc to flip

        # the 8 ray directions: (shift, mask that prevents wrap-around)
        # right(+1), left(-1), down(+8), up(-8), down-right(+9), up-left(-9), down-left(+7), up-right(-7)
        directions = [
            (1, 0xfefefefefefefefe),   # right (no wrap onto column 0)
            (-1, 0x7f7f7f7f7f7f7f7f),  # left (no wrap onto column 7)
            (8, 0xffffffffffffffff),   # down (cannot wrap, so all ones)
            (-8, 0xffffffffffffffff),  # up
            (9, 0xfefefefefefefefe),   # down-right
            (-9, 0x7f7f7f7f7f7f7f7f),  # up-left
            (7, 0x7f7f7f7f7f7f7f7f),   # down-left
            (-7, 0xfefefefefefefefe)   # up-right
        ]

        # cast a ray in each of the 8 directions
        for shift, mask in directions:
            current_flip = 0
            
            # advance the ray by one square
            if shift > 0:
                ray = (put_mask << shift) & mask
            else:
                ray = (put_mask >> abs(shift)) & mask

            # keep advancing while the ray passes opponent discs
            while (ray & opp_board) != 0:
                current_flip |= ray # remember the opponent discs passed
                if shift > 0:
                    ray = (ray << shift) & mask
                else:
                    ray = (ray >> abs(shift)) & mask

            # if the ray ends on one of our discs, the run is sandwiched
            if (ray & my_board) != 0:
                flipped_all |= current_flip # commit the recorded run

        return flipped_all # all discs to flip

    def put_disc(self, row, col, color):
        # discs this move would flip (64-bit mask)
        flip_mask = self.get_flip_mask(row, col, color)
        
        # a move that flips nothing is illegal
        if flip_mask == 0:
            return False

        # mask of the square being played
        pos = row * 8 + col
        put_mask = 1 << pos

        # XOR flips the color of all captured discs at once
        if color == 1:
            self.black |= put_mask      # 1. place our disc
            self.black ^= flip_mask     # 2. captured discs become black
            self.white ^= flip_mask     # 3. and are removed from white
        else:
            self.white |= put_mask
            self.white ^= flip_mask
            self.black ^= flip_mask

        return True
    
    def listUp(self, color):
        """
        Return the legal moves as a list [(row, col), ...] (in square-index order),
        for the AIs and the GUI.
        """
        # take the legal-move bits one at a time and convert them to coordinates
        legal = self.get_legal_board(color)
        moves = []
        while legal:
            low = legal & -legal  # lowest set bit
            i = low.bit_length() - 1
            moves.append((i // 8, i % 8))
            legal ^= low
        return moves

    def count_discs(self, color):
        """
        Count the discs of a color.
        """
        return (self.black if color == 1 else self.white).bit_count()
        
    def has_valid_move(self, color):
        """
        Whether `color` has at least one legal move (used to detect passes).
        """
        return self.get_legal_board(color) != 0
    
    def get_legal_board(self, color):
        my_board = self.black if color == 1 else self.white
        opp_board = self.white if color == 1 else self.black
        empty = ~(self.black | self.white)
        
        legal = 0
        direction =[
            (1, 0xfefefefefefefefe), (-1, 0x7f7f7f7f7f7f7f7f), # horizontal
            (8, 0xffffffffffffffff), (-8, 0xffffffffffffffff), # vertical
            (7, 0x7f7f7f7f7f7f7f7f), (9, 0xfefefefefefefefe),  # diagonal
            (-7, 0xfefefefefefefefe), (-9, 0x7f7f7f7f7f7f7f7f) # diagonal
        ]
        for shift, mask in direction:
            if shift > 0:
                tmp = (my_board << shift) & opp_board & mask
            else:
                tmp = (my_board >> abs(shift)) & opp_board &mask
            if tmp == 0:
                continue
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

    # as a @property, gui.py can keep reading it as board.grid
    @property
    def grid(self):
        """
        Convert the two 64-bit boards into an 8x8 NumPy array for drawing in the GUI.
        """
        import numpy as np  # drawing only; the engine itself (including the web version) does not need numpy

        grid_array = np.zeros((8, 8), dtype=int)

        for row in range(8):
            for col in range(8):
                # mask for this square
                pos = 1 << (row * 8 + col)

                # AND tells whether a black or white disc is there
                if self.black & pos:
                    grid_array[row, col] = 1
                elif self.white & pos:
                    grid_array[row, col] = -1

        return grid_array

    # print the board (for the terminal version, main.py)
    def display(self):
        grid = self.grid
        print("    a     b     c     d     e     f     g     h")
        for i in range(8):
            print(i + 1, end="   ")
            for j in range(8):
                if grid[i][j] == 0:
                    print(".", end="    ")
                elif grid[i][j] == 1:
                    print("●", end="     ")
                else:
                    print("○", end="     ")
            print("\n")
