# Turns the user's input into board coordinates
def parse_input(user_input):
    user_input = user_input.lower().replace(" ", "")

    if not (len(user_input) == 2 and ((user_input[0]  in "12345678" and user_input[1] in "abcdefgh") or(user_input[0] in "abcdefgh" and user_input[1] in "12345678"))):
        return None
    r_char = user_input[0] if user_input[0].isdigit() else user_input[1]
    c_char = user_input[1] if user_input[0].isdigit() else user_input[0]

    return int(r_char) -1, "abcdefgh".find(c_char)

class HumanPlayer:
    def __init__(self, color):
        self.color = color

    def get_move(self, board):
        while True:
            message = "Black (your turn): " if self.color == 1 else "White (your turn): "
            rc = input(message)

            if rc == 'q':
                return 'q'

            pos = parse_input(rc)
            if pos is None:
                print("Invalid input")
                continue

            return pos # a valid (row, col)