import sys

import pygame

from ai_manager import create_ai
from bitboard import BitBoard as Board

square_size = 80
board_px = square_size * 8
status_height = 50
screen_size = (board_px, board_px + status_height)
stone_radius = square_size // 2 - 5
fps = 60
green = (34, 139, 34)
dark_green = (20, 100, 20)
black = (0, 0, 0)
white = (255, 255, 255)
gray = (150, 150, 150)
hint_color = (60, 170, 60)


def draw_board(screen, board, hints=()):
    """盤面と石、置ける場所のヒントを描画する。"""
    screen.fill(green, pygame.Rect(0, 0, board_px, board_px))
    for i in range(9):
        pygame.draw.line(screen, black, (0, i * square_size), (board_px, i * square_size), 2)
        pygame.draw.line(screen, black, (i * square_size, 0), (i * square_size, board_px), 2)

    grid = board.grid  # 8x8 配列への変換は1フレームに1回だけ
    for row in range(8):
        for col in range(8):
            x = col * square_size + square_size // 2
            y = row * square_size + square_size // 2
            if grid[row, col] == 1:
                pygame.draw.circle(screen, black, (x, y), stone_radius)
            elif grid[row, col] == -1:
                pygame.draw.circle(screen, white, (x, y), stone_radius)

    for row, col in hints:
        x = col * square_size + square_size // 2
        y = row * square_size + square_size // 2
        pygame.draw.circle(screen, hint_color, (x, y), 8)


def draw_status(screen, font, board, message):
    """画面下部に石数と手番などのメッセージを表示する。"""
    screen.fill(dark_green, pygame.Rect(0, board_px, board_px, status_height))
    b, w = board.count_discs(1), board.count_discs(-1)
    score = font.render(f"Black {b} - {w} White", True, white)
    screen.blit(score, (12, board_px + 12))
    msg = font.render(message, True, white)
    screen.blit(msg, (board_px - msg.get_width() - 12, board_px + 12))


def quit_game():
    pygame.quit()
    sys.exit()


def main():
    pygame.display.init()
    pygame.font.init()

    screen = pygame.display.set_mode(screen_size)
    pygame.display.set_caption("Othello AI")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont(None, 36)
    title_font = pygame.font.SysFont(None, 60)

    game_state = "menu"
    board = Board()
    human_color = 0
    ai_color = 0
    ai_player = None
    current_color = 1
    message = ""

    button_black = pygame.Rect(200, 300, 240, 60)
    button_white = pygame.Rect(200, 400, 240, 60)

    while True:
        # ===== メニュー画面 =====
        if game_state == "menu":
            screen.fill(green)
            title_text = title_font.render("Othello AI", True, black)
            screen.blit(title_text, title_text.get_rect(center=(board_px // 2, 180)))

            pygame.draw.rect(screen, black, button_black)
            pygame.draw.rect(screen, white, button_white)
            text_black = font.render("Play BLACK (1st)", True, white)
            text_white = font.render("Play WHITE (2nd)", True, black)
            screen.blit(text_black, text_black.get_rect(center=button_black.center))
            screen.blit(text_white, text_white.get_rect(center=button_white.center))

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    quit_game()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if button_black.collidepoint(event.pos):
                        human_color = 1
                    elif button_white.collidepoint(event.pos):
                        human_color = -1
                    else:
                        continue
                    ai_color = -human_color
                    ai_player = create_ai("4", ai_color)
                    board = Board()
                    current_color = 1
                    message = ""
                    game_state = "playing"

        # ===== 対局画面 =====
        elif game_state == "playing":
            current_moves = board.listUp(current_color)

            if not current_moves and not board.has_valid_move(-current_color):
                game_state = "result"
                continue

            if not current_moves:
                message = "PASS (Black)" if current_color == 1 else "PASS (White)"
                current_color *= -1
                continue

            if current_color == human_color:
                if not message.startswith("PASS"):
                    message = "Your turn"
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        quit_game()
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        x, y = event.pos
                        if y >= board_px:
                            continue  # ステータスバーのクリックは無視
                        if board.put_disc(y // square_size, x // square_size, current_color):
                            current_color *= -1
                            message = ""
                draw_board(screen, board, hints=current_moves)
            else:
                # 「思考中」を表示してから AI に考えさせる
                draw_board(screen, board)
                draw_status(screen, font, board, "AI is thinking...")
                pygame.display.update()
                pygame.event.pump()

                best_move = ai_player.get_move(board)
                if best_move is not None:
                    board.put_disc(best_move[0], best_move[1], ai_color)
                current_color *= -1
                pygame.event.clear()  # 思考中のクリックを捨てる
                draw_board(screen, board)

            draw_status(screen, font, board, message)

        # ===== 結果画面 =====
        elif game_state == "result":
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    quit_game()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    game_state = "menu"

            draw_board(screen, board)
            draw_status(screen, font, board, "Click to restart")
            overlay = pygame.Surface((board_px, board_px))
            overlay.set_alpha(150)
            overlay.fill(black)
            screen.blit(overlay, (0, 0))

            black_count = board.count_discs(1)
            white_count = board.count_discs(-1)
            if black_count > white_count:
                result_text = "BLACK WINS!"
            elif white_count > black_count:
                result_text = "WHITE WINS!"
            else:
                result_text = "DRAW!"

            text_win = title_font.render(result_text, True, white)
            text_score = title_font.render(f"B:{black_count} - W:{white_count}", True, white)
            screen.blit(text_win, text_win.get_rect(center=(board_px // 2, 270)))
            screen.blit(text_score, text_score.get_rect(center=(board_px // 2, 340)))

        pygame.display.update()
        clock.tick(fps)


if __name__ == "__main__":
    main()
