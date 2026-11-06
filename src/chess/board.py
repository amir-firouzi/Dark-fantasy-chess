"""Complete chess board logic: state, move generation, validation, game status.

Implements standard chess rules on an 8x8 mailbox board:

- Legal move generation for all pieces (pawns, knights, bishops, rooks, queens, kings)
- Check, checkmate and stalemate detection
- Castling (both sides, with all legality conditions)
- En passant capture
- Pawn promotion
- Draw detection (fifty-move rule; repetition does not end the game)

The board is a plain Python list-of-lists of piece values (see ``constants``).
Row 0 is the top of the displayed board (Black's back rank from White's view).
"""

from __future__ import annotations

from typing import List, Optional, Set, Tuple

from . import constants as C

MoveKey = Tuple[int, int, int, int, int]  # from_row, from_col, to_row, to_col, promotion


class Move:
    """A fully described chess move."""

    __slots__ = ("from_row", "from_col", "to_row", "to_col", "promotion")

    def __init__(
        self,
        from_row: int,
        from_col: int,
        to_row: int,
        to_col: int,
        promotion: int = C.EMPTY,
    ) -> None:
        self.from_row = from_row
        self.from_col = from_col
        self.to_row = to_row
        self.to_col = to_col
        self.promotion = promotion

    def key(self) -> MoveKey:
        return (self.from_row, self.from_col, self.to_row, self.to_col, self.promotion)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Move):
            return NotImplemented
        return self.key() == other.key()

    def __hash__(self) -> int:
        return hash(self.key())

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        promo = ""
        if self.promotion:
            name = {C.WQ: "Q", C.WR: "R", C.WB: "B", C.WN: "N", C.BQ: "Q", C.BR: "R", C.BB: "B", C.BN: "N"}.get(self.promotion, "?")
            promo = f" promotion={name}"
        return f"Move({self.from_row},{self.from_col}->{self.to_row},{self.to_col}){promo}"


class GameStatus:
    """Outcome of a game: ongoing, checkmate, stalemate, draw."""

    def __init__(self, state: str = "ongoing") -> None:
        self.state = state  # ongoing | checkmate | stalemate | draw
        self.winner: Optional[int] = None  # C.WHITE / C.BLACK / None
        self.is_check: bool = False

    @property
    def is_over(self) -> bool:
        return self.state != "ongoing"


class Board:
    """The chess game state and rules engine."""

    def __init__(self) -> None:
        self.board: List[List[int]] = [[C.EMPTY] * 8 for _ in range(8)]
        self.reset()

    # ------------------------------------------------------------------ setup

    def reset(self) -> None:
        """Reset to the standard starting position."""
        self.board = [[C.EMPTY] * 8 for _ in range(8)]
        back_rank = [C.BR, C.BN, C.BB, C.BQ, C.BK, C.BB, C.BN, C.BR]
        self.board[0] = list(back_rank)
        self.board[7] = [C.WR, C.WN, C.WB, C.WQ, C.WK, C.WB, C.WN, C.WR]
        for col in range(8):
            self.board[1][col] = C.BP
            self.board[6][col] = C.WP

        self.turn = C.WHITE
        self.castling_rights: Set[str] = {"K", "Q", "k", "q"}
        self.en_passant: Optional[Tuple[int, int]] = None
        self.halfmove_clock = 0
        self.fullmove_number = 1
        self.move_history: List[MoveKey] = []
        self.position_counts: dict = {}
        self._last_move: Optional[Move] = None
        self._record_position()

    # ------------------------------------------------------------------ clone

    def clone(self) -> "Board":
        new_board = Board.__new__(Board)
        new_board.board = [row[:] for row in self.board]
        new_board.turn = self.turn
        new_board.castling_rights = set(self.castling_rights)
        new_board.en_passant = self.en_passant
        new_board.halfmove_clock = self.halfmove_clock
        new_board.fullmove_number = self.fullmove_number
        new_board.move_history = list(self.move_history)
        new_board.position_counts = dict(self.position_counts)
        new_board._last_move = self._last_move
        return new_board

    # --------------------------------------------------------- position key

    def position_key(self) -> str:
        parts = [
            self.turn == C.WHITE and "w" or "b",
            "rights:" + "".join(sorted(self.castling_rights)),
            "ep:" + (f"{self.en_passant[0]},{self.en_passant[1]}" if self.en_passant else "-"),
        ]
        for row in range(8):
            for col in range(8):
                p = self.board[row][col]
                if p == C.EMPTY:
                    parts.append(".")
                else:
                    cname = "W" if C.is_white_piece(p) else "B"
                    tname = "PNBRQK"[C.piece_type(p)]
                    parts.append(f"{cname}{tname}")
        return "".join(parts)

    def _record_position(self) -> None:
        key = self.position_key()
        self.position_counts[key] = self.position_counts.get(key, 0) + 1

    # ------------------------------------------------------------- move app

    def push_move(self, move: Move) -> None:
        """Apply a move to the board (mutates state)."""
        piece = self.board[move.from_row][move.from_col]
        captured = self.board[move.to_row][move.to_col]

        is_double_push = (
            piece in (C.WP, C.BP)
            and abs(move.to_row - move.from_row) == 2
            and move.to_col == move.from_col
        )
        is_ep_capture = (
            piece in (C.WP, C.BP)
            and captured == C.EMPTY
            and self.en_passant == (move.to_row, move.to_col)
            and abs(move.to_col - move.from_col) == 1
            and abs(move.to_row - move.from_row) == 1
        )

        # Place the moving piece (with promotion if any).
        self.board[move.to_row][move.to_col] = move.promotion if move.promotion else piece
        self.board[move.from_row][move.from_col] = C.EMPTY

        # En passant: remove the captured pawn, which sits behind the capturing
        # pawn's origin file (same row as the double-pushed pawn).
        if is_ep_capture:
            dc = move.to_col - move.from_col
            self.board[move.from_row][move.from_col + dc] = C.EMPTY

        # En passant target after a double push.
        if is_double_push:
            pawn_dir = -1 if piece == C.WP else 1
            self.en_passant = (move.from_row + pawn_dir, move.from_col)
        else:
            self.en_passant = None

        # Castling: move the rook as well.
        if piece in (C.WK, C.BK) and abs(move.to_col - move.from_col) == 2:
            row = move.from_row
            if move.to_col == 6:  # kingside
                self.board[row][5] = self.board[row][7]
                self.board[row][7] = C.EMPTY
            else:  # queenside
                self.board[row][3] = self.board[row][0]
                self.board[row][0] = C.EMPTY

        # Update castling rights.
        self._update_castling(move, piece, captured)

        self.turn = C.BLACK if self.turn == C.WHITE else C.WHITE
        if self.turn == C.WHITE:
            self.fullmove_number += 1

        self.halfmove_clock = 0 if (piece in (C.WP, C.BP) or captured) else self.halfmove_clock + 1
        self._last_move = move
        self._record_position()

    def _update_castling(self, move: Move, moved_piece: int, captured_piece: int) -> None:
        """Update castling rights using the pieces before the move is applied."""
        if moved_piece == C.WK:
            self.castling_rights.difference_update({"K", "Q"})
        elif moved_piece == C.BK:
            self.castling_rights.difference_update({"k", "q"})

        # A rook moving from its original corner forfeits that side's right.
        rook_rights = {
            (7, 0, C.WR): "Q",
            (7, 7, C.WR): "K",
            (0, 0, C.BR): "q",
            (0, 7, C.BR): "k",
        }
        right = rook_rights.get((move.from_row, move.from_col, moved_piece))
        if right:
            self.castling_rights.discard(right)

        # Capturing a rook on its original corner also removes its right.
        captured_right = rook_rights.get((move.to_row, move.to_col, captured_piece))
        if captured_right:
            self.castling_rights.discard(captured_right)

    # ------------------------------------------------------ move legality

    def generate_legal_moves(self) -> List[Move]:
        color = self.turn
        enemy = C.BLACK if color == C.WHITE else C.WHITE
        moves: List[Move] = []
        for row in range(8):
            for col in range(8):
                p = self.board[row][col]
                if not self._is_piece_of_color(p, color):
                    continue
                moves.extend(self._pseudo_moves(row, col, color, enemy))
        legal: List[Move] = []
        for m in moves:
            if self._is_legal(m):
                legal.append(m)
        return legal

    def _is_piece_of_color(self, p: int, color: int) -> bool:
        if color == C.WHITE:
            return 1 <= p <= 6
        return 7 <= p <= 12

    def _is_legal(self, move: Move) -> bool:
        """Validate movement rules and ensure the moving king remains safe."""
        if not (0 <= move.from_row < 8 and 0 <= move.from_col < 8
                and 0 <= move.to_row < 8 and 0 <= move.to_col < 8):
            return False
        if (move.from_row, move.from_col) == (move.to_row, move.to_col):
            return False

        piece = self.board[move.from_row][move.from_col]
        if not self._is_piece_of_color(piece, self.turn):
            return False
        target = self.board[move.to_row][move.to_col]
        # In chess the king is checkmated; it is never captured as a normal move.
        if target in (C.WK, C.BK):
            return False
        if self._is_piece_of_color(target, self.turn):
            return False

        enemy = C.BLACK if self.turn == C.WHITE else C.WHITE
        if move not in self._pseudo_moves(move.from_row, move.from_col, self.turn, enemy):
            return False

        mover_color = self.turn
        candidate = self.clone()
        candidate.push_move(move)
        return not candidate._is_in_check(mover_color)

    def _find_king(self, color: int) -> Tuple[int, int]:
        king_val = C.WK if color == C.WHITE else C.BK
        for row in range(8):
            for col in range(8):
                if self.board[row][col] == king_val:
                    return (row, col)
        return (-1, -1)

    def _is_in_check(self, color: int) -> bool:
        king_row, king_col = self._find_king(color)
        if king_row == -1:
            return False
        enemy = C.BLACK if color == C.WHITE else C.WHITE
        return self._is_square_attacked(king_row, king_col, enemy)

    def _is_square_attacked(self, row: int, col: int, by_color: int) -> bool:
        pawn = C.WP if by_color == C.WHITE else C.BP
        pawn_row_dir = -1 if by_color == C.WHITE else 1
        pr = row - pawn_row_dir
        for dc in (-1, 1):
            pc = col + dc
            if 0 <= pc < 8 and 0 <= pr < 8 and self.board[pr][pc] == pawn:
                return True
        knight = C.WN if by_color == C.WHITE else C.BN
        for dr, dc in ((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)):
            nr, nc = row + dr, col + dc
            if 0 <= nr < 8 and 0 <= nc < 8 and self.board[nr][nc] == knight:
                return True
        bishop = C.WB if by_color == C.WHITE else C.BB
        rook = C.WR if by_color == C.WHITE else C.BR
        queen = C.WQ if by_color == C.WHITE else C.BQ
        king = C.WK if by_color == C.WHITE else C.BK
        for dr, dc in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            r, c = row + dr, col + dc
            while 0 <= r < 8 and 0 <= c < 8:
                p = self.board[r][c]
                if p != C.EMPTY:
                    if p == bishop or p == queen:
                        return True
                    break
                r += dr
                c += dc
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            r, c = row + dr, col + dc
            while 0 <= r < 8 and 0 <= c < 8:
                p = self.board[r][c]
                if p != C.EMPTY:
                    if p == rook or p == queen:
                        return True
                    break
                r += dr
                c += dc
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = row + dr, col + dc
                if 0 <= nr < 8 and 0 <= nc < 8 and self.board[nr][nc] == king:
                    return True
        return False

    # ---------------------------------------------------------- pseudo moves

    def _pseudo_moves(self, row: int, col: int, color: int, enemy: int) -> List[Move]:
        p = self.board[row][col]
        ptype = C.piece_type(p)
        moves: List[Move] = []
        if ptype == C.PAWN:
            dir_ = -1 if color == C.WHITE else 1
            start_row = 6 if color == C.WHITE else 1
            promo_row = 0 if color == C.WHITE else 7
            one_row = row + dir_
            promo_pieces = (C.WQ, C.WR, C.WB, C.WN) if color == C.WHITE else (C.BQ, C.BR, C.BB, C.BN)
            if 0 <= one_row < 8 and self.board[one_row][col] == C.EMPTY:
                if one_row == promo_row:
                    for promo in promo_pieces:
                        moves.append(Move(row, col, one_row, col, promo))
                else:
                    moves.append(Move(row, col, one_row, col))
                    two_row = row + 2 * dir_
                    if row == start_row and self.board[two_row][col] == C.EMPTY:
                        moves.append(Move(row, col, two_row, col))
            for dc in (-1, 1):
                nc = col + dc
                tr = one_row
                if 0 <= nc < 8 and 0 <= tr < 8:
                    target = self.board[tr][nc]
                    is_ep = self.en_passant is not None and (tr, nc) == self.en_passant
                    if (target != C.EMPTY and self._is_piece_of_color(target, enemy)) or is_ep:
                        if tr == promo_row:
                            for promo in promo_pieces:
                                moves.append(Move(row, col, tr, nc, promo))
                        else:
                            moves.append(Move(row, col, tr, nc))
        elif ptype == C.KNIGHT:
            # Knights jump, so the landing square may be empty.
            for dr, dc in ((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)):
                nr, nc = row + dr, col + dc
                if 0 <= nr < 8 and 0 <= nc < 8:
                    moves.append(Move(row, col, nr, nc))
        elif ptype == C.BISHOP:
            moves.extend(self._slide_moves(row, col, enemy, (1, 1), (1, -1), (-1, 1), (-1, -1)))
        elif ptype == C.ROOK:
            moves.extend(self._slide_moves(row, col, enemy, (1, 0), (-1, 0), (0, 1), (0, -1)))
        elif ptype == C.QUEEN:
            moves.extend(self._slide_moves(row, col, enemy, (1, 1), (1, -1), (-1, 1), (-1, -1), (1, 0), (-1, 0), (0, 1), (0, -1)))
        elif ptype == C.KING:
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    if dr == 0 and dc == 0:
                        continue
                    nr, nc = row + dr, col + dc
                    if 0 <= nr < 8 and 0 <= nc < 8:
                        target = self.board[nr][nc]
                        if target == C.EMPTY or self._is_piece_of_color(target, enemy):
                            moves.append(Move(row, col, nr, nc))
            # Castling.
            if color == C.WHITE and row == 7 and col == 4:
                if (
                    "K" in self.castling_rights
                    and self.board[7][5] == C.EMPTY
                    and self.board[7][6] == C.EMPTY
                    and self.board[7][7] == C.WR
                    and self._castle_safe(7, 4, 7, 6)
                ):
                    moves.append(Move(7, 4, 7, 6))
            if (
                color == C.WHITE
                and row == 7
                and col == 4
                and "Q" in self.castling_rights
                and self.board[7][1] == C.EMPTY
                and self.board[7][2] == C.EMPTY
                and self.board[7][3] == C.EMPTY
                and self.board[7][0] == C.WR
                and self._castle_safe(7, 4, 7, 2)
            ):
                moves.append(Move(7, 4, 7, 2))
            if color == C.BLACK and row == 0 and col == 4:
                if (
                    "k" in self.castling_rights
                    and self.board[0][5] == C.EMPTY
                    and self.board[0][6] == C.EMPTY
                    and self.board[0][7] == C.BR
                    and self._castle_safe(0, 4, 0, 6)
                ):
                    moves.append(Move(0, 4, 0, 6))
            if (
                color == C.BLACK
                and row == 0
                and col == 4
                and "q" in self.castling_rights
                and self.board[0][1] == C.EMPTY
                and self.board[0][2] == C.EMPTY
                and self.board[0][3] == C.EMPTY
                and self.board[0][0] == C.BR
                and self._castle_safe(0, 4, 0, 2)
            ):
                moves.append(Move(0, 4, 0, 2))
        return moves

    def _slide_moves(self, row: int, col: int, enemy: int, *dirs: Tuple[int, int]) -> List[Move]:
        moves: List[Move] = []
        for dr, dc in dirs:
            r, c = row + dr, col + dc
            while 0 <= r < 8 and 0 <= c < 8:
                target = self.board[r][c]
                if target == C.EMPTY:
                    moves.append(Move(row, col, r, c))
                elif self._is_piece_of_color(target, enemy):
                    moves.append(Move(row, col, r, c))
                    break
                else:
                    break
                r += dr
                c += dc
        return moves

    def _castle_safe(self, king_from_row: int, king_from_col: int, king_to_row: int, king_to_col: int) -> bool:
        """Castling legality: king must not be in check, nor pass through, nor land on an attacked square."""
        enemy = C.BLACK if self.turn == C.WHITE else C.WHITE
        if self._is_square_attacked(king_from_row, king_from_col, enemy):
            return False
        if self._is_square_attacked(king_to_row, king_to_col, enemy):
            return False
        if king_to_col > king_from_col:  # kingside: transit through col+1, col+2
            transit_cols = (king_from_col + 1, king_from_col + 2)
        else:  # queenside: transit through col-1, col-2
            transit_cols = (king_from_col - 1, king_from_col - 2)
        for c in transit_cols:
            if self._is_square_attacked(king_from_row, c, enemy):
                return False
        return True

    # ------------------------------------------------------------- game over

    def get_status(self) -> GameStatus:
        """Compute the current game status (check / checkmate / stalemate / draw)."""
        legal = self.generate_legal_moves()
        in_check = self._is_in_check(self.turn)
        if not legal:
            if in_check:
                # The current side to move is checkmated.
                status = GameStatus("checkmate")
                status.winner = C.BLACK if self.turn == C.WHITE else C.WHITE
            else:
                status = GameStatus("stalemate")
            status.is_check = in_check
            return status
        status = GameStatus("ongoing")
        status.is_check = in_check
        if self.halfmove_clock >= 100:
            status.state = "draw"
            status.winner = None
        return status
