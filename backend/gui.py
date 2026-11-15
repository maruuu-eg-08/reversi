import pygame
import sys
import numpy as np
print("1: numpyまでOK")

from bitboard import BitBoard as Board
print("2: bitboard import OK")

from alphabeta_ai import AlphaBetaAI
print("3: alphabeta_ai import OK")

square_size = 80
screen_size = square_size * 8
stone_radius = square_size // 2 - 5
fps = 60
green = (34,139,34)
black = (0,0,0)
white = (255,255,255)
gray = (150, 150, 150)

# 描画専用の関数（スッキリさせるために上にまとめました）
def draw_board(screen, board):
    screen.fill(green)
    for i in range(9):
        pygame.draw.line(screen, black, (0, i*square_size),(screen_size, i * square_size), 2)
        pygame.draw.line(screen, black, (i * square_size, 0), (i * square_size, screen_size), 2)

    for row in range(8):
        for col in range(8):
            x = col * square_size + (square_size // 2)
            y = row * square_size + (square_size // 2)
            if board.grid[row, col] == 1:
                pygame.draw.circle(screen, black, (x, y), 35, width = 0)
            elif board.grid[row, col] == -1:
                pygame.draw.circle(screen, white, (x, y), 35, width = 0)

def main():
    print("4: main開始")
    
    # 修正ポイント：全体初期化ではなく、必要なものだけ個別に起動
    try:
        pygame.display.init() # 画面機能だけ起動
        pygame.font.init()    # 文字機能だけ起動
        print("5: pygame.display & font init OK")
    except Exception as e:
        print(f"初期化エラーが発生しました: {e}")
        return

    board = Board()
    print("6: Board生成OK")
    
    screen = pygame.display.set_mode((screen_size, screen_size))
    print("7: set_mode OK")
    pygame.display.set_caption("最強オセロAI")
    clock = pygame.time.Clock()
    
    # フォントの読み込み（Noneでデフォルトを使用）
    font = pygame.font.SysFont(None, 40)
    title_font = pygame.font.SysFont(None, 60)
    
    game_state = "menu"
    human_color = 0
    ai_color = 0
    ai_player = None
    current_color = 1

    while True:
        # ==========================================
        # 🎮 シーン1：メニュー画面
        # ==========================================
        if game_state == "menu":
            screen.fill(green)
            title_text = title_font.render("Othello AI", True, black)
            screen.blit(title_text, (200, 150))

            button_black = pygame.Rect(200, 300, 240, 60)
            button_white = pygame.Rect(200, 400, 240, 60)
            pygame.draw.rect(screen, black, button_black)
            pygame.draw.rect(screen, white, button_white)

            text_black = font.render("Play BLACK (1st)", True, white)
            text_white = font.render("Play WHITE (2nd)", True, black)
            screen.blit(text_black, (215, 315))
            screen.blit(text_white, (215, 415))

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    pos = pygame.mouse.get_pos()
                    if button_black.collidepoint(pos):
                        human_color = 1
                        ai_color = -1
                        ai_player = AlphaBetaAI(ai_color, 4) # 🌟AI生成
                        game_state = "Playing"
                    elif button_white.collidepoint(pos):
                        human_color = -1
                        ai_color = 1
                        ai_player = AlphaBetaAI(ai_color, 4) # 🌟AI生成
                        game_state = "Playing"

        # ==========================================
        # 🎮 シーン2：対局画面
        # ==========================================
        elif game_state == "Playing":
            current_moves = board.listUp(current_color)
            opponent_moves = board.listUp(current_color * -1)

            if len(current_moves) == 0 and len(opponent_moves) == 0:
                game_state = "result"
            
            elif len(current_moves) == 0:
                print(f"パス！")
                current_color *= -1
            
            else:
                # --- A. 人間のターン ---
                if current_color == human_color:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            pygame.quit()
                            sys.exit()
                        if event.type == pygame.MOUSEBUTTONDOWN:
                            x, y = pygame.mouse.get_pos()
                            col = x // square_size
                            row = y // square_size
                            # 自分のターンかつ、石が置けた場合のみ交代
                            if board.put_disc(row, col, current_color):
                                current_color *= -1

                # --- B. AIのターン ---
                elif current_color == ai_color:
                    # 1. まず盤面を最新状態にして「思考中」を出す
                    draw_board(screen, board)
                    thinking_text = font.render("AI is thinking...", True, white, black)
                    screen.blit(thinking_text, (10, 10))
                    pygame.display.update()

                    # 2. Windowsに「フリーズしてないよ」と伝える（重要）
                    pygame.event.pump() 

                    # 3. AIの思考（ここが長い場合に備える）
                    best_move = ai_player.get_move(board)
                    
                    if best_move is not None:
                        row, col = best_move
                        board.put_disc(row, col, ai_color)
                    
                    current_color *= -1
                    
                    # AIが置いた後、一度イベントを空にする（連打防止）
                    pygame.event.clear()

            # 描画
            draw_board(screen, board)

        # ==========================================
        # 🎮 シーン3：結果発表（リザルト画面）
        # ==========================================
        elif game_state == "result":
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

            # 盤面を描画した上に、半透明の黒い幕をかぶせる
            draw_board(screen, board)
            overlay = pygame.Surface((screen_size, screen_size))
            overlay.set_alpha(150)
            overlay.fill(black)
            screen.blit(overlay, (0, 0))

            # NumPyで石を数える
            black_count = np.sum(board.grid == 1)
            white_count = np.sum(board.grid == -1)

            if black_count > white_count:
                result_text = "BLACK WINS!"
            elif white_count > black_count:
                result_text = "WHITE WINS!"
            else:
                result_text = "DRAW!"

            text_win = title_font.render(result_text, True, white)
            text_score = title_font.render(f"B:{black_count} - W:{white_count}", True, white)

            screen.blit(text_win, (180, 250))
            screen.blit(text_score, (190, 320))

        # ==========================================
        # 🔄 画面の更新（毎フレーム必ず呼ばれる）
        # ==========================================
        pygame.display.update()
        clock.tick(fps)

if __name__ == "__main__":
    main()