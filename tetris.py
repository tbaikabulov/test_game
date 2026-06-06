from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pygame

COLS = 10
ROWS = 20
BLOCK = 30
SIDEBAR = 220
WIDTH = COLS * BLOCK + SIDEBAR * 2
HEIGHT = ROWS * BLOCK

FPS = 60
LOCK_MS = 500
MAX_LOCK_MOVES = 15
SCORE_TABLE = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}

COLORS = {
    "bg": (15, 17, 23),
    "panel": (26, 29, 39),
    "panel2": (37, 42, 56),
    "border": (58, 65, 88),
    "text": (232, 236, 244),
    "muted": (139, 147, 168),
    "accent": (91, 140, 255),
    "grid": (255, 255, 255, 12),
    "ghost": (255, 255, 255, 55),
}

SHAPES = {
    "I": {"color": (0, 229, 255), "matrix": [[0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 0, 0], [0, 0, 0, 0]]},
    "O": {"color": (255, 213, 79), "matrix": [[1, 1], [1, 1]]},
    "T": {"color": (179, 136, 255), "matrix": [[0, 1, 0], [1, 1, 1], [0, 0, 0]]},
    "S": {"color": (105, 240, 174), "matrix": [[0, 1, 1], [1, 1, 0], [0, 0, 0]]},
    "Z": {"color": (255, 82, 82), "matrix": [[1, 1, 0], [0, 1, 1], [0, 0, 0]]},
    "J": {"color": (68, 138, 255), "matrix": [[1, 0, 0], [1, 1, 1], [0, 0, 0]]},
    "L": {"color": (255, 145, 0), "matrix": [[0, 0, 1], [1, 1, 1], [0, 0, 0]]},
}

PIECE_TYPES = list(SHAPES.keys())


@dataclass
class Piece:
    type: str
    matrix: List[List[int]]
    color: Tuple[int, int, int]
    x: int = 0
    y: int = 0

    @classmethod
    def create(cls, piece_type: str) -> "Piece":
        shape = SHAPES[piece_type]
        return cls(
            type=piece_type,
            matrix=[row[:] for row in shape["matrix"]],
            color=shape["color"],
            x=(COLS - len(shape["matrix"][0])) // 2,
            y=0,
        )

    def clone(self) -> "Piece":
        return Piece(self.type, [row[:] for row in self.matrix], self.color, self.x, self.y)


@dataclass
class GameState:
    board: List[List[Optional[Tuple[int, int, int]]]] = field(default_factory=lambda: [[None] * COLS for _ in range(ROWS)])
    current: Optional[Piece] = None
    next_piece: Piece = field(default_factory=lambda: Piece.create(random.choice(PIECE_TYPES)))
    hold: Optional[str] = None
    can_hold: bool = True
    score: int = 0
    level: int = 1
    lines: int = 0
    drop_interval: int = 1000
    last_drop: int = 0
    status: str = "idle"
    lock_started: Optional[int] = None
    lock_moves: int = 0
    soft_drop: bool = False


def rotate_matrix(matrix: List[List[int]]) -> List[List[int]]:
    size = len(matrix)
    rotated = [[0] * size for _ in range(size)]
    for y in range(size):
        for x in range(size):
            rotated[x][size - 1 - y] = matrix[y][x]
    return rotated


def collides(board: list, piece: Piece, dx: int = 0, dy: int = 0, matrix: Optional[List[List[int]]] = None) -> bool:
    matrix = matrix or piece.matrix
    for y, row in enumerate(matrix):
        for x, cell in enumerate(row):
            if not cell:
                continue
            board_x = piece.x + x + dx
            board_y = piece.y + y + dy
            if board_x < 0 or board_x >= COLS or board_y >= ROWS:
                return True
            if board_y >= 0 and board[board_y][board_x] is not None:
                return True
    return False


def ghost_y(board: list, piece: Piece) -> int:
    y = piece.y
    while not collides(board, piece, dy=y - piece.y + 1):
        y += 1
    return y


def spawn_piece(state: GameState) -> None:
    state.current = state.next_piece
    state.next_piece = Piece.create(random.choice(PIECE_TYPES))
    state.can_hold = True
    state.lock_started = None
    state.lock_moves = 0
    if state.current and collides(state.board, state.current):
        state.status = "gameover"


def clear_lines(state: GameState) -> None:
    cleared = 0
    y = ROWS - 1
    while y >= 0:
        if all(cell is not None for cell in state.board[y]):
            del state.board[y]
            state.board.insert(0, [None] * COLS)
            cleared += 1
        else:
            y -= 1

    if cleared:
        state.lines += cleared
        state.score += SCORE_TABLE.get(cleared, 800) * state.level
        state.level = state.lines // 10 + 1
        state.drop_interval = max(100, 1000 - (state.level - 1) * 80)


def lock_piece(state: GameState) -> None:
    piece = state.current
    if not piece:
        return

    for y, row in enumerate(piece.matrix):
        for x, cell in enumerate(row):
            if not cell:
                continue
            board_y = piece.y + y
            board_x = piece.x + x
            if board_y < 0:
                state.status = "gameover"
                return
            state.board[board_y][board_x] = piece.color

    clear_lines(state)
    spawn_piece(state)


def reset_lock(state: GameState) -> None:
    if state.lock_started is not None and state.lock_moves < MAX_LOCK_MOVES:
        state.lock_moves += 1
        state.lock_started = pygame.time.get_ticks()


def move_piece(state: GameState, dx: int) -> None:
    if state.status != "playing" or not state.current:
        return
    if not collides(state.board, state.current, dx=dx):
        state.current.x += dx
        reset_lock(state)


def soft_drop_piece(state: GameState) -> None:
    if state.status != "playing" or not state.current:
        return
    if not collides(state.board, state.current, dy=1):
        state.current.y += 1
        state.score += 1
        reset_lock(state)
    else:
        handle_grounded(state)


def hard_drop_piece(state: GameState) -> None:
    if state.status != "playing" or not state.current:
        return
    target = ghost_y(state.board, state.current)
    state.score += (target - state.current.y) * 2
    state.current.y = target
    lock_piece(state)


def rotate_piece(state: GameState) -> None:
    if state.status != "playing" or not state.current:
        return
    rotated = rotate_matrix(state.current.matrix)
    for kick in (0, -1, 1, -2, 2):
        if not collides(state.board, state.current, dx=kick, matrix=rotated):
            state.current.matrix = rotated
            state.current.x += kick
            reset_lock(state)
            return


def hold_piece(state: GameState) -> None:
    if state.status != "playing" or not state.current or not state.can_hold:
        return

    state.can_hold = False
    current_type = state.current.type
    if state.hold:
        state.current = Piece.create(state.hold)
    else:
        state.current = state.next_piece
        state.next_piece = Piece.create(random.choice(PIECE_TYPES))

    state.hold = current_type
    state.current.y = 0
    state.current.x = (COLS - len(state.current.matrix[0])) // 2
    state.lock_started = None
    state.lock_moves = 0

    if collides(state.board, state.current):
        state.status = "gameover"


def handle_grounded(state: GameState) -> None:
    now = pygame.time.get_ticks()
    if state.lock_started is None:
        state.lock_started = now
        state.lock_moves = 0
        return
    if now - state.lock_started >= LOCK_MS:
        lock_piece(state)


def start_game(state: GameState) -> None:
    state.board = [[None] * COLS for _ in range(ROWS)]
    state.next_piece = Piece.create(random.choice(PIECE_TYPES))
    state.hold = None
    state.can_hold = True
    state.score = 0
    state.level = 1
    state.lines = 0
    state.drop_interval = 1000
    state.last_drop = pygame.time.get_ticks()
    state.lock_started = None
    state.lock_moves = 0
    state.soft_drop = False
    state.status = "playing"
    spawn_piece(state)


def toggle_pause(state: GameState) -> None:
    if state.status == "playing":
        state.status = "paused"
    elif state.status == "paused":
        state.status = "playing"
        state.last_drop = pygame.time.get_ticks()


def update_game(state: GameState) -> None:
    if state.status != "playing" or not state.current:
        return

    now = pygame.time.get_ticks()
    interval = 50 if state.soft_drop else state.drop_interval

    if not collides(state.board, state.current, dy=1):
        if now - state.last_drop >= interval:
            state.current.y += 1
            state.last_drop = now
            state.lock_started = None
    else:
        handle_grounded(state)


def draw_block(surface: pygame.Surface, px: int, py: int, color: Tuple[int, int, int], size: int = BLOCK, alpha: int = 255) -> None:
    rect = pygame.Rect(px + 1, py + 1, size - 2, size - 2)
    block = pygame.Surface((size - 2, size - 2), pygame.SRCALPHA)
    block.fill((*color, alpha))
    highlight = pygame.Surface((size - 2, 4), pygame.SRCALPHA)
    highlight.fill((255, 255, 255, 45 if alpha == 255 else 20))
    block.blit(highlight, (0, 0))
    surface.blit(block, rect.topleft)


def draw_piece(surface: pygame.Surface, piece: Piece, origin_x: int = 0, origin_y: int = 0, size: int = BLOCK, alpha: int = 255) -> None:
    for y, row in enumerate(piece.matrix):
        for x, cell in enumerate(row):
            if cell:
                draw_block(
                    surface,
                    origin_x + (piece.x + x) * size,
                    origin_y + (piece.y + y) * size,
                    piece.color,
                    size,
                    alpha,
                )


def draw_preview(surface: pygame.Surface, piece: Optional[Piece], rect: pygame.Rect) -> None:
    pygame.draw.rect(surface, COLORS["panel2"], rect, border_radius=10)
    pygame.draw.rect(surface, COLORS["border"], rect, 1, border_radius=10)
    if not piece:
        return

    size = 22
    matrix = piece.matrix
    offset_x = rect.x + (rect.width - len(matrix[0]) * size) // 2
    offset_y = rect.y + (rect.height - len(matrix) * size) // 2
    for y, row in enumerate(matrix):
        for x, cell in enumerate(row):
            if cell:
                block_rect = pygame.Rect(offset_x + x * size + 1, offset_y + y * size + 1, size - 2, size - 2)
                pygame.draw.rect(surface, piece.color, block_rect, border_radius=3)
                pygame.draw.rect(surface, (255, 255, 255, 40), block_rect.inflate(-block_rect.width + 4, -block_rect.height + 4))


def draw_text(surface: pygame.Surface, font: pygame.font.Font, text: str, pos: Tuple[int, int], color: Tuple[int, int, int]) -> None:
    surface.blit(font.render(text, True, color), pos)


def draw_sidebar(surface: pygame.Surface, state: GameState, fonts: Dict[str, pygame.font.Font]) -> None:
    left = pygame.Rect(16, 16, SIDEBAR - 32, HEIGHT - 32)
    right = pygame.Rect(WIDTH - SIDEBAR + 16, 16, SIDEBAR - 32, HEIGHT - 32)
    for panel in (left, right):
        pygame.draw.rect(surface, COLORS["panel"], panel, border_radius=14)
        pygame.draw.rect(surface, COLORS["border"], panel, 1, border_radius=14)

    y = 36
    for label, value in (("Счёт", str(state.score)), ("Уровень", str(state.level)), ("Линии", str(state.lines))):
        draw_text(surface, fonts["label"], label, (36, y), COLORS["muted"])
        draw_text(surface, fonts["value"], value, (36, y + 22), COLORS["text"])
        y += 72

    draw_text(surface, fonts["label"], "Следующая", (36, y), COLORS["muted"])
    draw_preview(surface, state.next_piece, pygame.Rect(36, y + 24, 120, 120))

    draw_text(surface, fonts["label"], "Удержание", (36, y + 160), COLORS["muted"])
    hold_piece = Piece.create(state.hold) if state.hold else None
    draw_preview(surface, hold_piece, pygame.Rect(36, y + 184, 120, 120))

    controls = [
        "Управление",
        "← → — движение",
        "↑ — поворот",
        "↓ — ускорение",
        "Space — сброс",
        "C — удержание",
        "P — пауза",
        "Enter — старт",
        "Esc — выход",
    ]
    cy = 40
    for i, line in enumerate(controls):
        font = fonts["title"] if i == 0 else fonts["small"]
        color = COLORS["muted"] if i == 0 else COLORS["text"]
        draw_text(surface, font, line, (WIDTH - SIDEBAR + 36, cy), color)
        cy += 28 if i == 0 else 24


def draw_board(surface: pygame.Surface, state: GameState) -> None:
    board_rect = pygame.Rect(SIDEBAR, 0, COLS * BLOCK, ROWS * BLOCK)
    pygame.draw.rect(surface, (10, 12, 18), board_rect)
    pygame.draw.rect(surface, COLORS["border"], board_rect, 2)

    grid_color = (255, 255, 255, 12)
    for x in range(COLS + 1):
        pygame.draw.line(surface, grid_color, (SIDEBAR + x * BLOCK, 0), (SIDEBAR + x * BLOCK, HEIGHT))
    for y in range(ROWS + 1):
        pygame.draw.line(surface, grid_color, (SIDEBAR, y * BLOCK), (SIDEBAR + COLS * BLOCK, y * BLOCK))

    for y, row in enumerate(state.board):
        for x, color in enumerate(row):
            if color:
                draw_block(surface, SIDEBAR + x * BLOCK, y * BLOCK, color)

    if state.current:
        ghost = state.current.clone()
        ghost.y = ghost_y(state.board, ghost)
        draw_piece(surface, ghost, SIDEBAR, 0, alpha=70)
        draw_piece(surface, state.current, SIDEBAR, 0)


def draw_overlay(surface: pygame.Surface, state: GameState, fonts: Dict[str, pygame.font.Font]) -> None:
    if state.status == "playing":
        return

    overlay = pygame.Surface((COLS * BLOCK, HEIGHT), pygame.SRCALPHA)
    overlay.fill((10, 12, 18, 210))
    surface.blit(overlay, (SIDEBAR, 0))

    if state.status == "idle":
        title, subtitle, button = "Тетрис", "Нажмите Enter, чтобы начать", "Играть"
    elif state.status == "paused":
        title, subtitle, button = "Пауза", "Нажмите P, чтобы продолжить", ""
    else:
        title, subtitle, button = "Игра окончена", f"Счёт: {state.score}", "Enter — заново"

    title_surf = fonts["overlay_title"].render(title, True, COLORS["text"])
    subtitle_surf = fonts["overlay_text"].render(subtitle, True, COLORS["muted"])
    surface.blit(title_surf, title_surf.get_rect(center=(SIDEBAR + COLS * BLOCK // 2, HEIGHT // 2 - 40)))
    surface.blit(subtitle_surf, subtitle_surf.get_rect(center=(SIDEBAR + COLS * BLOCK // 2, HEIGHT // 2 + 4)))

    if button:
        btn_rect = pygame.Rect(0, 0, 160, 44)
        btn_rect.center = (SIDEBAR + COLS * BLOCK // 2, HEIGHT // 2 + 56)
        pygame.draw.rect(surface, COLORS["accent"], btn_rect, border_radius=10)
        btn_text = fonts["button"].render(button, True, (255, 255, 255))
        surface.blit(btn_text, btn_text.get_rect(center=btn_rect.center))


def handle_key(state: GameState, event: pygame.event.Event) -> None:
    if event.key == pygame.K_ESCAPE:
        pygame.quit()
        sys.exit()

    if event.key == pygame.K_RETURN:
        if state.status in ("idle", "gameover"):
            start_game(state)
        return

    if event.key == pygame.K_p:
        if state.status in ("playing", "paused"):
            toggle_pause(state)
        return

    if state.status != "playing":
        return

    if event.key == pygame.K_LEFT:
        move_piece(state, -1)
    elif event.key == pygame.K_RIGHT:
        move_piece(state, 1)
    elif event.key == pygame.K_DOWN:
        soft_drop_piece(state)
    elif event.key == pygame.K_UP:
        rotate_piece(state)
    elif event.key == pygame.K_SPACE:
        hard_drop_piece(state)
    elif event.key == pygame.K_c:
        hold_piece(state)


def main() -> None:
    pygame.init()
    pygame.display.set_caption("Тетрис")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    fonts = {
        "label": pygame.font.SysFont("arial", 14, bold=True),
        "value": pygame.font.SysFont("arial", 28, bold=True),
        "title": pygame.font.SysFont("arial", 16, bold=True),
        "small": pygame.font.SysFont("arial", 15),
        "overlay_title": pygame.font.SysFont("arial", 42, bold=True),
        "overlay_text": pygame.font.SysFont("arial", 18),
        "button": pygame.font.SysFont("arial", 18, bold=True),
    }

    state = GameState()
    state.next_piece = Piece.create(random.choice(PIECE_TYPES))

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                handle_key(state, event)
            elif event.type == pygame.KEYUP and event.key == pygame.K_DOWN:
                state.soft_drop = False

        if pygame.key.get_pressed()[pygame.K_DOWN] and state.status == "playing":
            state.soft_drop = True
            soft_drop_piece(state)

        update_game(state)

        screen.fill(COLORS["bg"])
        draw_sidebar(screen, state, fonts)
        draw_board(screen, state)
        draw_overlay(screen, state, fonts)
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


if __name__ == "__main__":
    main()

# command to run the game: python tetris.py