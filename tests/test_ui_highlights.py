"""UI highlight logic tests; these do not require an initialized display."""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    import pygame  # noqa: F401
except ModuleNotFoundError:
    # The tested helpers only use the chess engine; pygame is needed only by drawing methods.
    sys.modules["pygame"] = types.ModuleType("pygame")

from ui.game import DarkFantasyChess, CAPTURE_HIGHLIGHT, CHECK_HIGHLIGHT
from chess import Board, Move
from chess import constants as C


def empty_board():
    board = Board()
    board.board = [[C.EMPTY] * 8 for _ in range(8)]
    board.castling_rights = set()
    board.en_passant = None
    return board


def test_capture_destination_is_classified_red():
    game = DarkFantasyChess.__new__(DarkFantasyChess)
    game.board = empty_board()
    game.board.board[7][4] = C.WK
    game.board.board[0][7] = C.BK
    game.board.board[4][0] = C.WR
    game.board.board[4][4] = C.BP
    game.board.turn = C.WHITE

    capture = Move(4, 0, 4, 4)
    highlights, checked_king = game._classify_selected_moves([capture])

    assert highlights[(4, 4)] == CAPTURE_HIGHLIGHT
    assert checked_king is None


def test_check_giving_move_is_not_purple_before_it_is_played():
    game = DarkFantasyChess.__new__(DarkFantasyChess)
    game.board = empty_board()
    game.board.board[7][4] = C.WK
    game.board.board[0][4] = C.BK
    game.board.board[4][0] = C.WR
    game.board.turn = C.WHITE

    checking_move = Move(4, 0, 0, 0)
    highlights, checked_king = game._classify_selected_moves([checking_move])

    assert highlights == {}
    assert checked_king is None


def test_all_checkmating_attackers_are_found():
    game = DarkFantasyChess.__new__(DarkFantasyChess)
    game.board = empty_board()
    game.board.board[7][4] = C.WK
    game.board.board[0][4] = C.BK
    game.board.board[4][4] = C.BR
    game.board.board[4][0] = C.BQ
    game.board.turn = C.WHITE

    attackers = game._checking_pieces(C.BLACK, (7, 4))
    assert (4, 4) in attackers
    assert (4, 0) not in attackers


def test_checkmate_sequence_marks_attackers_purple_and_king_red():
    from chess.board import GameStatus

    game = DarkFantasyChess.__new__(DarkFantasyChess)
    game.board = empty_board()
    game.board.board[7][4] = C.WK
    game.board.board[0][0] = C.BK
    game.board.board[4][4] = C.BR
    game.board.turn = C.WHITE
    game.pending_end_status = None
    game.pending_end_started = None
    game.pending_end_highlights = {}
    game.selected = None
    game.legal_moves = []
    game.legal_move_highlights = {}
    game.checking_king_square = None
    played = []
    game.play_sound = played.append

    game._start_end_sequence(GameStatus("checkmate"))

    assert game.pending_end_highlights[(4, 4)] == CHECK_HIGHLIGHT
    assert game.pending_end_highlights[(7, 4)] == CAPTURE_HIGHLIGHT
    assert played == ["checkmate"]


def test_draw_sequence_marks_both_kings_green_and_uses_mate_sound():
    from chess.board import GameStatus
    from ui.game import DRAW_HIGHLIGHT

    game = DarkFantasyChess.__new__(DarkFantasyChess)
    game.board = empty_board()
    game.board.board[7][4] = C.WK
    game.board.board[0][4] = C.BK
    game.board.turn = C.WHITE
    game.pending_end_status = None
    game.pending_end_started = None
    game.pending_end_highlights = {}
    game.selected = None
    game.legal_moves = []
    game.legal_move_highlights = {}
    game.checking_king_square = None
    played = []
    game.play_sound = played.append

    game._start_end_sequence(GameStatus("draw"))

    assert game.pending_end_highlights[(7, 4)] == DRAW_HIGHLIGHT
    assert game.pending_end_highlights[(0, 4)] == DRAW_HIGHLIGHT
    assert played == ["checkmate"]
