from bitboard import BitBoard as Board
from player import HumanPlayer
from ai_manager import create_ai

def setup_game():
    while True:
        level_choice = input("CPUのレベルを選んでください（1: 弱い, 2: 強い, 3: めっちゃ強い, 4: 超強い）:")
        turn_choice = input("あなたは先攻(黒)と後攻(白)どちらにしますか？（1: 先攻, 2: 後攻）:")
        #入力された値が正しい範囲に入っているかどうかのチェック
        if not (len(level_choice) == 1 and level_choice in "1234" and len(turn_choice) == 1 and turn_choice in "12") :
            print("正しい値を入力してください")
            continue

        if turn_choice == "1":
            player_black = HumanPlayer(1)
            player_white = create_ai(level_choice, -1)
        elif turn_choice == "2":
            player_white = HumanPlayer(-1)
            player_black = create_ai(level_choice, 1)

        return player_black, player_white

board = Board()



player_black, player_white = setup_game()
current_color = 1

while True:
    #有効手がない場合の処理
    if not board.has_valid_move(current_color):
        print("置ける場所がないため、パスします！")
        current_color *= -1
        #相手も有効手がない場合はゲーム終了
        if not board.has_valid_move(current_color):
            print("ゲーム終了！")
            break
        else:#相手に有効手がある場合は続ける
            continue
    board.display()


    if current_color == 1:
        current_player = player_black
    else:
        current_player = player_white

    if type(current_player) is not HumanPlayer:
        if current_color == 1:
            print("黒(AI)が深く考えています・・")
        else:
            print("白(AI)が深く考えています・・")
    move = current_player.get_move(board)

    if move == 'q':
        break

    row, col = move
    if not board.put_disc(row, col, current_color):
        print("そこには置けません")
        continue
    else:
        print("プレイヤーを交代します")
        current_color *= -1

bc = board.count_discs(1)
wc = board.count_discs(-1)
print(f"黒: {bc}枚, 白: {wc}枚")

if bc == wc:
    rs = "引き分けです！"
elif bc > wc:
    rs = "黒の勝ちです！"
else:
    rs = "白の勝ちです！"

print(rs)