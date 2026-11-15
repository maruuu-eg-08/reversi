from ai_manager import create_ai
from bitboard import BitBoard as Board
from player import HumanPlayer


def setup_game():
    while True:
        level_choice = input("Choose the CPU level (1: weak, 2: strong, 3: very strong, 4: strongest): ")
        turn_choice = input("Play first (black) or second (white)? (1: first, 2: second): ")
        # validate the input
        if not (len(level_choice) == 1 and level_choice in "1234" and len(turn_choice) == 1 and turn_choice in "12") :
            print("Please enter a valid value")
            continue

        if turn_choice == "1":
            player_black = HumanPlayer(1)
            player_white = create_ai(level_choice, -1)
        elif turn_choice == "2":
            player_white = HumanPlayer(-1)
            player_black = create_ai(level_choice, 1)

        return player_black, player_white

def main():
    board = Board()

    player_black, player_white = setup_game()
    current_color = 1

    while True:
        # no legal move
        if not board.has_valid_move(current_color):
            print("No legal move: pass!")
            current_color *= -1
            # the game ends if the opponent cannot move either
            if not board.has_valid_move(current_color):
                print("Game over!")
                break
            else:# the opponent can move, so continue
                continue
        board.display()

        if current_color == 1:
            current_player = player_black
        else:
            current_player = player_white

        if type(current_player) is not HumanPlayer:
            if current_color == 1:
                print("Black (AI) is thinking...")
            else:
                print("White (AI) is thinking...")
        move = current_player.get_move(board)

        if move == 'q':
            print("Game aborted")
            return

        row, col = move
        if not board.put_disc(row, col, current_color):
            print("You cannot play there")
            continue
        else:
            print("Switching players")
            current_color *= -1

    bc = board.count_discs(1)
    wc = board.count_discs(-1)
    print(f"Black: {bc}, White: {wc}")

    if bc == wc:
        rs = "Draw!"
    elif bc > wc:
        rs = "Black wins!"
    else:
        rs = "White wins!"

    print(rs)


if __name__ == "__main__":
    main()
