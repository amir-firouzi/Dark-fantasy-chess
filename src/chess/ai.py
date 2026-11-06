"""Lightweight chess AI using negamax, alpha-beta and iterative deepening."""
from __future__ import annotations

import random
import time
from typing import List, Optional

from . import constants as C
from .board import Board, Move

MATERIAL_VALUES = {
    C.PAWN: 100, C.KNIGHT: 320, C.BISHOP: 330,
    C.ROOK: 500, C.QUEEN: 900, C.KING: 0,
}

_PST_DATA = {
    C.PAWN: [0,0,0,0,0,0,0,0, 50,50,50,50,50,50,50,50, 10,10,20,30,30,20,10,10, 5,5,10,25,25,10,5,5, 0,0,0,20,20,0,0,0, 5,-5,-10,0,0,-10,-5,5, 5,10,10,-20,-20,10,10,5, 0,0,0,0,0,0,0,0],
    C.KNIGHT: [-50,-40,-30,-30,-30,-30,-40,-50, -40,-20,0,0,0,0,-20,-40, -30,0,10,15,15,10,0,-30, -30,5,15,20,20,15,5,-30, -30,0,15,20,20,15,0,-30, -30,5,15,20,20,15,5,-30, -30,0,10,15,15,10,0,-30, -50,-40,-30,-30,-30,-30,-40,-50],
    C.BISHOP: [20,30,10,0,0,10,30,20, -10,-20,-20,-20,-20,-20,-20,-10, -10,-20,-20,-20,-20,-20,-20,-10, -10,-20,-20,-20,-20,-20,-20,-10, -10,-20,-20,-20,-20,-20,-20,-10, -10,-20,-20,-20,-20,-20,-20,-10, -10,-20,-20,-20,-20,-20,-20,-10, 20,30,10,0,0,10,30,20],
    C.ROOK: [0,0,0,0,0,0,0,0, 5,10,10,10,10,10,10,5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, -5,0,0,0,0,0,0,-5, 0,0,0,5,5,0,0,0],
    C.QUEEN: [-20,-10,-10,-5,-5,-10,-10,-20, -10,0,0,0,0,0,0,-10, -10,0,5,5,5,5,0,-10, -5,0,5,5,5,5,0,-5, 0,0,5,5,5,5,0,-5, -10,5,5,5,5,5,0,-10, -10,0,5,0,0,0,0,-10, -20,-10,-10,-5,-5,-10,-10,-20],
    C.KING: [-30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30, -30,-40,-40,-50,-50,-40,-40,-30, -20,-30,-30,-40,-40,-30,-30,-20, -10,-20,-20,-20,-20,-20,-20,-10, 20,20,0,0,0,0,20,20, 20,30,10,0,0,10,30,20],
}
PST = _PST_DATA
MATE_SCORE = 100_000


class _SearchTimeout(Exception):
    pass


def _evaluate_white(board: Board) -> int:
    score = 0
    for row in range(8):
        for col in range(8):
            piece = board.board[row][col]
            if piece == C.EMPTY:
                continue
            ptype = C.piece_type(piece)
            table_row = 7 - row if C.is_black_piece(piece) else row
            value = MATERIAL_VALUES[ptype] + PST[ptype][table_row * 8 + col]
            score += -value if C.is_black_piece(piece) else value
    return score


def _evaluate(board: Board, color: int) -> int:
    score = _evaluate_white(board)
    return score if color == C.WHITE else -score


def _move_order_score(board: Board, move: Move) -> int:
    target = board.board[move.to_row][move.to_col]
    attacker = board.board[move.from_row][move.from_col]
    score = 0
    if target != C.EMPTY:
        score += 10 * MATERIAL_VALUES[C.piece_type(target)] - MATERIAL_VALUES[C.piece_type(attacker)]
    if move.promotion:
        score += MATERIAL_VALUES[C.piece_type(move.promotion)]
    return score


def _ordered_moves(board: Board, moves: List[Move]) -> List[Move]:
    return sorted(moves, key=lambda m: _move_order_score(board, m), reverse=True)


def _check_deadline(deadline: Optional[float]) -> None:
    if deadline is not None and time.monotonic() >= deadline:
        raise _SearchTimeout


def _quiescence(board: Board, alpha: int, beta: int, color: int,
                deadline: Optional[float], remaining: int = 5) -> int:
    _check_deadline(deadline)
    in_check = board._is_in_check(color)
    stand_pat = _evaluate(board, color)
    if remaining <= 0:
        return stand_pat

    if not in_check:
        if stand_pat >= beta:
            return beta
        alpha = max(alpha, stand_pat)
        moves = [m for m in board.generate_legal_moves()
                 if board.board[m.to_row][m.to_col] != C.EMPTY or m.promotion]
    else:
        # A checked king must consider every legal evasion, not only captures.
        moves = board.generate_legal_moves()
        if not moves:
            return -MATE_SCORE

    best = -10**9 if in_check else stand_pat
    for move in _ordered_moves(board, moves):
        _check_deadline(deadline)
        child = board.clone()
        child.push_move(move)
        score = -_quiescence(child, -beta, -alpha, C.opponent(color), deadline, remaining - 1)
        best = max(best, score)
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def _negamax(board: Board, depth: int, alpha: int, beta: int,
             color: int, deadline: Optional[float], ply: int = 0) -> int:
    _check_deadline(deadline)
    moves = board.generate_legal_moves()
    if not moves:
        return -MATE_SCORE + ply if board._is_in_check(color) else 0
    if depth <= 0:
        return _quiescence(board, alpha, beta, color, deadline)

    best = -10**9
    for move in _ordered_moves(board, moves):
        _check_deadline(deadline)
        child = board.clone()
        child.push_move(move)
        score = -_negamax(child, depth - 1, -beta, -alpha,
                          C.opponent(color), deadline, ply + 1)
        best = max(best, score)
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def _search_root(board: Board, depth: int, deadline: Optional[float]) -> Move:
    color = board.turn
    moves = _ordered_moves(board, board.generate_legal_moves())
    if not moves:
        raise ValueError("No legal moves available")
    best_move = moves[0]
    best_score = -10**9
    alpha, beta = -10**9, 10**9
    for move in moves:
        _check_deadline(deadline)
        child = board.clone()
        child.push_move(move)
        score = -_negamax(child, depth - 1, -beta, -alpha,
                          C.opponent(color), deadline, 1)
        if score > best_score:
            best_score, best_move = score, move
        alpha = max(alpha, score)
    return best_move


def _easy_move(board: Board, legal: List[Move]) -> Move:
    """Prefer sensible one-ply moves, but deliberately keep some variety."""
    scored = []
    color = board.turn
    for move in legal:
        child = board.clone()
        child.push_move(move)
        # A shallow reply search discourages hanging valuable pieces.
        replies = child.generate_legal_moves()
        if not replies:
            score = MATE_SCORE if child._is_in_check(C.opponent(color)) else 0
        elif replies:
            opponent_best = -10**9
            for reply in replies:
                reply_board = child.clone()
                reply_board.push_move(reply)
                opponent_best = max(opponent_best, _evaluate(reply_board, C.opponent(color)))
            score = -opponent_best
        else:
            score = _evaluate(child, color)
        score += random.randint(-35, 35)
        scored.append((score, move))
    scored.sort(key=lambda item: item[0], reverse=True)
    # Pick randomly among the better half to retain an easy, less predictable style.
    pool = scored[:max(1, (len(scored) + 1) // 2)]
    return random.choice(pool)[1]


def find_best_move(board: Board, difficulty: str) -> Optional[Move]:
    """Return a legal move for the side to move."""
    legal = board.generate_legal_moves()
    if not legal:
        return None
    level = (difficulty or "normal").lower()
    if level == "easy":
        return _easy_move(board, legal)
    if level == "normal":
        # Fixed depth keeps response time predictable on low-end computers.
        try:
            return _search_root(board, 2, time.monotonic() + 1.5)
        except _SearchTimeout:
            return random.choice(legal)

    # Hard uses iterative deepening. Keep the last fully completed iteration.
    deadline = time.monotonic() + 3.0
    best_move = legal[0]
    for depth in (2, 3, 4, 5):
        try:
            best_move = _search_root(board, depth, deadline)
        except _SearchTimeout:
            break
    return best_move
