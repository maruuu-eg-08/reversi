#ユーザからの入力を配列のインデックス番号に変える関数
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
            message = "黒（あなたのターンです）:" if self.color == 1 else "白（あなたのターンです）"
            rc = input(message)

            if rc == 'q':
                return 'q'

            pos = parse_input(rc)
            if pos is None:
                print("無効な入力です")
                continue

            return pos #正常な座標を(row, col)で返す