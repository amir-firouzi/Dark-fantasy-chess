"""Constants and piece definitions for the chess engine."""

# Board is an 8x8 grid. Row 0 is the top of the board (Black's back rank
# from White's perspective). Column 0 is file 'a'.

EMPTY = 0

# White pieces occupy values 1-6, Black pieces occupy values 7-12.
WP, WN, WB, WR, WQ, WK = 1, 2, 3, 4, 5, 6
BP, BN, BB, BR, BQ, BK = 7, 8, 9, 10, 11, 12

# Color enum used across the engine.
WHITE = 0
BLACK = 1

# Piece-type enum (0=pawn ... 5=king), independent of color.
PAWN = 0
KNIGHT = 1
BISHOP = 2
ROOK = 3
QUEEN = 4
KING = 5

# Unicode-like short names for debugging / FEN-ish labels.
PIECE_NAMES = {
    (WHITE, PAWN): "P",
    (WHITE, KNIGHT): "N",
    (WHITE, BISHOP): "B",
    (WHITE, ROOK): "R",
    (WHITE, QUEEN): "Q",
    (WHITE, KING): "K",
    (BLACK, PAWN): "p",
    (BLACK, KNIGHT): "n",
    (BLACK, BISHOP): "b",
    (BLACK, ROOK): "r",
    (BLACK, QUEEN): "q",
    (BLACK, KING): "k",
}


def is_white_piece(value: int) -> bool:
    """Return True if the piece value represents a white piece."""
    return 1 <= value <= 6


def is_black_piece(value: int) -> bool:
    """Return True if the piece value represents a black piece."""
    return 7 <= value <= 12


def piece_color(value: int) -> int:
    """Return WHITE(0) or BLACK(1) for a piece value."""
    return WHITE if is_white_piece(value) else BLACK


def piece_type(value: int) -> int:
    """Return the type of a piece (PAWN..KING)."""
    if is_white_piece(value):
        return value - 1
    return value - 7


def make_piece(color: int, ptype: int) -> int:
    """Create a piece value from a color and type."""
    if color == WHITE:
        return ptype + 1
    return ptype + 7


def opponent(color: int) -> int:
    """Return the opposing color."""
    return BLACK if color == WHITE else WHITE
