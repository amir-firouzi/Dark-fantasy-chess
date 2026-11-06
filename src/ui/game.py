"""Dark Fantasy Chess graphical game, built with pygame-ce."""
from __future__ import annotations

import sys
import time
import random
import threading
import math
import json
from pathlib import Path
from typing import Optional

import pygame

from chess import Board, Move, C
from chess.ai import find_best_move

WIDTH, HEIGHT = 1280, 800
FPS = 60
BG = (7, 7, 9)                 # plain black background, as requested
PANEL = (17, 16, 19)
PANEL_2 = (25, 23, 27)
GOLD = (190, 157, 99)
PALE_GOLD = (225, 204, 160)
RED = (119, 31, 39)
TEXT = (226, 220, 207)
MUTED = (137, 131, 125)
LIGHT_SQUARE = (174, 158, 133)
DARK_SQUARE = (66, 58, 54)
SELECT = (206, 164, 74)
LEGAL = (110, 160, 112)
CAPTURE_HIGHLIGHT = (220, 55, 62)
CHECK_HIGHLIGHT = (153, 82, 220)
DRAW_HIGHLIGHT = (65, 190, 105)

PIECE_LABEL = {
    C.WP: "P", C.WN: "N", C.WB: "B", C.WR: "R", C.WQ: "Q", C.WK: "K",
    C.BP: "P", C.BN: "N", C.BB: "B", C.BR: "R", C.BQ: "Q", C.BK: "K",
}
PIECE_NAMES = {
    C.PAWN: "Pawn", C.KNIGHT: "Knight", C.BISHOP: "Bishop",
    C.ROOK: "Rook", C.QUEEN: "Queen", C.KING: "King",
}
PROMOTIONS = [("Queen", C.QUEEN), ("Rook", C.ROOK),
              ("Bishop", C.BISHOP), ("Knight", C.KNIGHT)]


def shade_color(color, amount):
    return tuple(max(0, min(255, c + amount)) for c in color)


class DarkFantasyChess:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Dark Fantasy Chess")
        self.windowed_size = (WIDTH, HEIGHT)
        self.fullscreen = False
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
        # In a PyInstaller build, persist settings beside the executable rather
        # than inside the temporary extraction directory (_MEIPASS).
        if getattr(sys, "frozen", False):
            self.settings_path = Path(sys.executable).resolve().parent / "settings.json"
        else:
            self.settings_path = Path(__file__).resolve().parents[2] / "settings.json"
        self.fallback_settings_path = Path.home() / ".dark_fantasy_chess" / "settings.json"
        self.settings = self._load_settings()
        self.theme_options = ["Default", "Wood", "Royal", "Abyss", "Empire"]
        self.theme_dropdown_open = False
        self.settings_controls = {}
        self.sound_bank = {}
        self._load_sounds()
        self.clock = pygame.time.Clock()
        self.font_cache = {}
        self.piece_cache = {}
        self.piece_images = self._load_piece_images()
        self.tile_cache = {}
        self.material_cache = {}
        self.state = "menu"
        self.menu_choice = 0
        self.mode = "two_players"
        self.difficulty = "normal"
        self.player_color = C.WHITE
        self.board = Board()
        self.selected = None
        self.legal_moves = []
        self.legal_move_highlights = {}
        self.checking_king_square = None
        self.current_check_highlights = {}
        self.pending_end_status = None
        self.pending_end_started = None
        self.pending_end_highlights = {}
        self.result_board_back_rect = None
        self.last_move = None
        # Each half-move is stored separately: (side, notation).
        self.move_text = []
        self.history_scroll = 0
        self.history_view_rect = None
        self.start_time = 0.0
        self.elapsed = 0.0
        self.ai_thread = None
        self.ai_result = None
        self.ai_thinking = False
        self.ai_error = None
        self.pending_promotion = None
        self.end_reason = ""
        self.winner_text = ""
        self.result_scroll = 0
        self.move_animation = None
        self.animation_duration = 0.20
        self.pause_started = None
        self.pause_return_state = "game"
        self.pause_buttons = []
        self.pause_button_rect = None
        if self.settings.get("fullscreen", False):
            self.fullscreen = False
            self.toggle_fullscreen()

    def _load_settings(self):
        defaults = {"sound": True, "animations": True, "theme": "Default", "fullscreen": False}
        valid_themes = ("Default", "Wood", "Royal", "Abyss", "Empire")
        # Prefer the project-local file, but also support a per-user fallback when
        # the game is installed in a read-only directory.
        for candidate in (self.settings_path, self.fallback_settings_path):
            try:
                if candidate.is_file():
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        defaults["sound"] = bool(data.get("sound", defaults["sound"]))
                        defaults["animations"] = bool(data.get("animations", defaults["animations"]))
                        defaults["fullscreen"] = bool(data.get("fullscreen", defaults["fullscreen"]))
                        theme = data.get("theme", defaults["theme"])
                        if theme in valid_themes:
                            defaults["theme"] = theme
                        break
            except (OSError, ValueError, TypeError):
                continue
        return defaults

    def save_settings(self):
        payload = json.dumps(self.settings, ensure_ascii=False, indent=2)
        # Atomic write prevents a partially written settings file if the game
        # closes while saving. Fall back to the user's profile if needed.
        for destination in (self.settings_path, self.fallback_settings_path):
            temp_path = destination.with_suffix(destination.suffix + ".tmp")
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                temp_path.write_text(payload, encoding="utf-8")
                temp_path.replace(destination)
                return
            except OSError as exc:
                try:
                    if temp_path.exists():
                        temp_path.unlink()
                except OSError:
                    pass
                print(f"Could not save settings to {destination}: {exc}")

    def _load_piece_images(self):
        """Load and alpha-trim the supplied PNG artwork, keyed by chess value."""
        asset_dir = Path(__file__).resolve().parent / "assets" / "pieces"
        names = {
            C.WP: "white_pawn.png", C.WN: "white_knight.png",
            C.WB: "white_bishop.png", C.WR: "white_rook.png",
            C.WQ: "white_queen.png", C.WK: "white_king.png",
            C.BP: "black_pawn.png", C.BN: "black_knight.png",
            C.BB: "black_bishop.png", C.BR: "black_rook.png",
            C.BQ: "black_queen.png", C.BK: "black_king.png",
        }
        loaded = {}
        for value, filename in names.items():
            path = asset_dir / filename
            if not path.is_file():
                continue
            try:
                image = pygame.image.load(str(path)).convert_alpha()
                bounds = image.get_bounding_rect(min_alpha=8)
                if bounds.width and bounds.height:
                    image = image.subsurface(bounds).copy()
                loaded[value] = image
            except (pygame.error, OSError) as exc:
                print(f"Could not load piece artwork {path}: {exc}")
        missing = len(names) - len(loaded)
        if missing:
            print(f"Piece artwork: loaded {len(loaded)}/12 images; {missing} will use fallback artwork.")
        else:
            print("Piece artwork: all 12 custom PNG images loaded.")
        return loaded

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.font_cache:
            self.font_cache[key] = pygame.font.SysFont("georgia", size, bold=bold)
        return self.font_cache[key]

    def text(self, surface, value, size, color=TEXT, center=None, topleft=None, bold=False):
        img = self.font(size, bold).render(str(value), True, color)
        rect = img.get_rect()
        if center:
            rect.center = center
        elif topleft:
            rect.topleft = topleft
        surface.blit(img, rect)
        return rect

    def button(self, rect, label, hover=False, accent=False):
        color = (38, 30, 29) if hover else PANEL_2
        pygame.draw.rect(self.screen, color, rect, border_radius=5)
        pygame.draw.rect(self.screen, GOLD if accent or hover else (77, 68, 58), rect, 2, border_radius=5)
        self.text(self.screen, label, max(18, int(rect.height * .34)),
                  PALE_GOLD if hover or accent else TEXT, center=rect.center, bold=True)

    def centered_buttons(self, labels, mouse, accent_first=False):
        """Draw a vertical button list; only the main menu accents its first item."""
        w, h, gap = 310, 58, 18
        x = (self.screen.get_width() - w) // 2
        y = int(self.screen.get_height() * .43)
        rects = []
        for i, label in enumerate(labels):
            r = pygame.Rect(x, y + i * (h + gap), w, h)
            self.button(r, label, r.collidepoint(mouse), accent_first and i == 0)
            rects.append(r)
        return rects

    def draw_menu(self, mouse):
        self.screen.fill(BG)
        w, h = self.screen.get_size()
        self.text(self.screen, "DARK FANTASY CHESS", 48, PALE_GOLD,
                  center=(w // 2, max(110, h // 5)), bold=True)
        pygame.draw.line(self.screen, GOLD, (w//2-170, max(145, h//5+35)),
                         (w//2+170, max(145, h//5+35)), 2)
        self.text(self.screen, "A GAME OF STRATEGY", 15, MUTED,
                  center=(w//2, max(170, h//5+65)))
        return self.centered_buttons(["START", "SETTINGS", "EXIT"], mouse,
                                     accent_first=True)

    def draw_settings(self, mouse):
        self.screen.fill(BG)
        w, h = self.screen.get_size()
        self.text(self.screen, "SETTINGS", 42, PALE_GOLD, center=(w//2, 105), bold=True)
        rows = [
            ("SOUND EFFECTS", "ON" if self.settings["sound"] else "OFF", "sound"),
            ("MOVE ANIMATIONS", "ON" if self.settings["animations"] else "OFF", "animations"),
            ("BOARD THEME", self.settings["theme"], "theme"),
            ("FULLSCREEN", "ON" if self.fullscreen else "OFF", "fullscreen"),
        ]
        self.settings_controls = {}
        x, y, row_w, row_h = w//2-250, 185, 500, 66
        for i, (label, value, key) in enumerate(rows):
            row = pygame.Rect(x, y+i*88, row_w, row_h)
            pygame.draw.rect(self.screen, PANEL, row, border_radius=6)
            pygame.draw.rect(self.screen, (76,65,55), row, 1, border_radius=6)
            self.text(self.screen, label, 18, PALE_GOLD, topleft=(row.x+20,row.y+22), bold=True)
            control = pygame.Rect(row.right-175,row.y+10,155,46)
            self.button(control, value + ("  ▾" if key == "theme" else ""), control.collidepoint(mouse), False)
            self.settings_controls[key] = control
        if self.theme_dropdown_open:
            anchor = self.settings_controls["theme"]
            # Float to the right of the theme row, away from the Fullscreen control.
            popup_x = min(anchor.right + 12, w - 190)
            popup_y = anchor.y - 8
            for i, theme in enumerate(self.theme_options):
                option = pygame.Rect(popup_x, popup_y+i*39, 178, 36)
                pygame.draw.rect(self.screen, PANEL_2, option, border_radius=3)
                pygame.draw.rect(self.screen, GOLD if theme == self.settings["theme"] else (76,65,55), option, 1, border_radius=3)
                self.text(self.screen, theme, 16, PALE_GOLD, center=option.center)
                self.settings_controls[f"theme_{i}"] = option
        back = pygame.Rect(w//2-145,h-100,290,54)
        self.button(back,"BACK",back.collidepoint(mouse),False)
        self.settings_controls["back"] = back
        return list(self.settings_controls.values())

    def _load_sounds(self):
        """Load the five sound effects supplied by the user."""
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            sound_dir = Path(__file__).resolve().parent / "assets" / "sounds"
            for name in ("move1", "move2", "move3", "check", "checkmate"):
                path = sound_dir / f"{name}.wav"
                if path.is_file():
                    self.sound_bank[name] = pygame.mixer.Sound(str(path))
                else:
                    print(f"Missing sound asset: {path}")
        except pygame.error as exc:
            print(f"Audio unavailable: {exc}")
            self.sound_bank = {}

    def play_sound(self, name):
        if not self.settings.get("sound", True):
            return
        if name == "move":
            choices = [key for key in ("move1", "move2", "move3") if key in self.sound_bank]
            sound = self.sound_bank.get(random.choice(choices)) if choices else None
        else:
            sound = self.sound_bank.get(name)
        if sound:
            try:
                sound.play()
            except pygame.error:
                pass

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.windowed_size = self.screen.get_size()
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        self.font_cache.clear()
        self.piece_cache.clear()
        self.tile_cache.clear()
        self.material_cache.clear()
        self.settings["fullscreen"] = self.fullscreen
        self.save_settings()

    def draw_choice(self, title, options, mouse, subtitle=None, horizontal_count=0):
        self.screen.fill(BG)
        w, h = self.screen.get_size()
        self.text(self.screen, title, 40, PALE_GOLD, center=(w//2, 170), bold=True)
        if subtitle:
            self.text(self.screen, subtitle, 17, MUTED, center=(w//2, 210))

        if horizontal_count <= 0:
            return self.centered_buttons(options, mouse)

        # The primary choices share one row; secondary actions such as BACK stay below.
        count = min(horizontal_count, len(options))
        button_h = 58
        gap = 22
        button_w = 230 if count == 2 else 190
        total_w = count * button_w + (count - 1) * gap
        start_x = (w - total_w) // 2
        y = int(h * .43)
        rects = []
        for i, label in enumerate(options[:count]):
            rect = pygame.Rect(start_x + i * (button_w + gap), y, button_w, button_h)
            self.button(rect, label, rect.collidepoint(mouse), False)
            rects.append(rect)

        for i, label in enumerate(options[count:]):
            rect = pygame.Rect(w//2 - 145, y + button_h + 24 + i * 72, 290, 54)
            self.button(rect, label, rect.collidepoint(mouse), False)
            rects.append(rect)
        return rects

    def begin_game(self, color):
        self.player_color = color
        self.board = Board()
        self.selected = None
        self.legal_moves = []
        self.legal_move_highlights = {}
        self.checking_king_square = None
        self.current_check_highlights = {}
        self.pending_end_status = None
        self.pending_end_started = None
        self.pending_end_highlights = {}
        self.last_move = None
        self.move_text = []
        self.history_scroll = 0
        self.history_view_rect = None
        self.start_time = time.monotonic()
        self.elapsed = 0.0
        self.pause_started = None
        self.ai_result = None
        self.ai_thinking = False
        self.ai_error = None
        self.pending_promotion = None
        self.move_animation = None
        self.state = "game"
        self._maybe_start_ai()

    def _maybe_start_ai(self):
        """Start exactly one background search whenever it is the AI's turn."""
        if (self.state != "game" or self.pending_end_status is not None
                or self.mode != "ai" or self.board.turn == self.player_color):
            return
        if self.ai_thinking or self.ai_result is not None:
            return
        snapshot = self.board.clone()
        difficulty = self.difficulty
        self.ai_thinking = True
        self.ai_error = None

        def worker():
            result = None
            try:
                result = find_best_move(snapshot, difficulty)
            except Exception as exc:
                result = exc
            self.ai_result = result
            self.ai_thinking = False

        self.ai_thread = threading.Thread(target=worker, name="ChessAI", daemon=True)
        self.ai_thread.start()

    def square_at(self, pos, board_rect, flipped=False):
        if not board_rect.collidepoint(pos):
            return None
        size = board_rect.width // 8
        col = (pos[0] - board_rect.x) // size
        row = (pos[1] - board_rect.y) // size
        if flipped:
            row, col = 7-row, 7-col
        return int(row), int(col)

    def screen_square(self, row, col, flipped, board_rect):
        if flipped:
            row, col = 7-row, 7-col
        s = board_rect.width // 8
        return pygame.Rect(board_rect.x + col*s, board_rect.y + row*s, s, s)

    def _piece_sprite(self, value, size):
        """Cached, original vector-style gothic chess artwork."""
        key = (value, size)
        if key in self.piece_cache:
            return self.piece_cache[key]
        custom = self.piece_images.get(value)
        if custom is not None:
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            # Keep each piece proportional and align its feet/base consistently.
            max_w = max(1, int(size * 0.88))
            max_h = max(1, int(size * 0.88))
            scale = min(max_w / custom.get_width(), max_h / custom.get_height())
            target = (max(1, round(custom.get_width() * scale)),
                      max(1, round(custom.get_height() * scale)))
            artwork = pygame.transform.smoothscale(custom, target)
            surf.blit(artwork, artwork.get_rect(midbottom=(size // 2, int(size * 0.94))))
            self.piece_cache[key] = surf
            return surf
        # Procedural fallback remains available if an individual PNG is missing.
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        white = C.is_white_piece(value)
        kind = C.piece_type(value)
        cx = cy = size // 2
        k = size / 100.0
        stone = (222, 211, 188) if white else (54, 50, 53)
        edge = (112, 83, 52) if white else (154, 48, 52)
        shade = (83, 69, 57) if white else (17, 14, 17)
        glint = (255, 239, 203) if white else (111, 91, 91)
        crimson = (151, 39, 47)

        def xy(x, y):
            return int(cx+x*k), int(cy+y*k)
        def poly(points, fill=stone, outline=edge, width=2):
            pts=[xy(x,y) for x,y in points]
            pygame.draw.polygon(surf, fill, pts)
            if outline:
                pygame.draw.polygon(surf, outline, pts, max(1,int(width*k)))
        def ln(points, color=glint, width=2):
            pygame.draw.lines(surf,color,False,[xy(x,y) for x,y in points],max(1,int(width*k)))
        def circle(x,y,r,color,outline=None):
            pygame.draw.circle(surf,color,xy(x,y),max(1,int(r*k)))
            if outline:
                pygame.draw.circle(surf,outline,xy(x,y),max(1,int(r*k)),max(1,int(k)))

        # Shared plinth, bevels and engraved front jewel.
        pygame.draw.ellipse(surf,(0,0,0,110),(int(cx-36*k),int(cy+28*k),int(72*k),int(13*k)))
        poly([(-34,28),(-29,19),(-22,15),(22,15),(29,19),(34,28),(26,35),(-26,35)],stone)
        ln([(-27,23),(-17,19),(17,19),(27,23)],glint,1)
        poly([(-22,15),(-17,8),(17,8),(22,15)],shade,edge,1)
        circle(0,25,3,crimson,(72,20,25))

        if kind == C.PAWN:
            poly([(-17,9),(-14,-3),(-8,-12),(8,-12),(14,-3),(17,9)])
            circle(0,-22,13,stone,edge)
            circle(-4,-26,3,glint)
            ln([(-11,3),(0,-1),(11,3)],glint,1)
        elif kind == C.KNIGHT:
            # Angular horse-head silhouette with armored crest and eye.
            poly([(-21,14),(-18,3),(-23,-7),(-15,-17),(-10,-29),(2,-37),(17,-31),(24,-19),(14,-11),(20,-1),(13,13),(3,16)])
            poly([(-10,-28),(-5,-40),(8,-35),(17,-25),(7,-21),(-1,-24)],shade,crimson,1)
            poly([(5,-19),(20,-17),(29,-10),(16,-7),(7,-10)],stone)
            circle(10,-23,3,crimson)
            ln([(-17,-9),(-9,-3),(-3,7)],glint,2)
        elif kind == C.BISHOP:
            poly([(-18,13),(-15,0),(-10,-12),(-5,-22),(0,-36),(5,-22),(10,-12),(15,0),(18,13)])
            pygame.draw.ellipse(surf,shade,(int(cx-9*k),int(cy-35*k),int(18*k),int(26*k)))
            pygame.draw.ellipse(surf,crimson,(int(cx-5*k),int(cy-31*k),int(10*k),int(18*k)),max(1,int(2*k)))
            ln([(-8,-12),(0,-19),(8,-12)],glint,2)
            ln([(0,-34),(0,-8)],glint,1)
        elif kind == C.ROOK:
            poly([(-20,14),(-17,-22),(17,-22),(20,14)])
            poly([(-24,-20),(-24,-35),(-13,-35),(-13,-27),(-5,-27),(-5,-35),(5,-35),(5,-27),(13,-27),(13,-35),(24,-35),(24,-20)])
            pygame.draw.rect(surf,crimson,(int(cx-3*k),int(cy-17*k),max(1,int(6*k)),max(1,int(29*k))))
            ln([(-13,-13),(-9,7),(9,7),(13,-13)],glint,1)
        elif kind == C.QUEEN:
            poly([(-21,13),(-17,-8),(-12,-1),(-7,-18),(0,-7),(7,-18),(12,-1),(17,-8),(21,13)])
            for x,y in [(-17,-17),(-8,-25),(0,-33),(8,-25),(17,-17)]:
                circle(x,y,4,crimson,edge)
            ln([(-13,6),(0,1),(13,6)],glint,2)
            pygame.draw.arc(surf,edge,(int(cx-13*k),int(cy-17*k),int(26*k),int(22*k)),.2,2.9,max(1,int(2*k)))
        elif kind == C.KING:
            poly([(-20,14),(-17,-19),(-12,-26),(12,-26),(17,-19),(20,14)])
            poly([(-12,-26),(-8,-33),(8,-33),(12,-26)],shade,crimson,1)
            pygame.draw.rect(surf,crimson,(int(cx-3*k),int(cy-48*k),max(1,int(6*k)),max(1,int(29*k))))
            pygame.draw.rect(surf,glint,(int(cx-13*k),int(cy-39*k),max(1,int(26*k)),max(1,int(6*k))))
            circle(0,-47,4,crimson,edge)
            ln([(-12,-14),(0,-19),(12,-14)],glint,2)

        self.piece_cache[key]=surf
        return surf

    def draw_piece(self, value, rect):
        if value == C.EMPTY:
            return
        size=max(24,rect.width)
        sprite=self._piece_sprite(value,size)
        self.screen.blit(sprite,sprite.get_rect(center=rect.center))

    def _wood_board_texture(self, board_rect):
        """Create one continuous walnut surface so grain never repeats per square."""
        key = ("Wood", board_rect.width, board_rect.height)
        cached = self.material_cache.get(key)
        if cached is not None:
            return cached
        width, height = board_rect.size
        surface = pygame.Surface((width, height))
        surface.fill((49, 27, 18))
        rng = random.Random(71023 + width * 13 + height)
        # Broad, flowing walnut ribbons span the complete 8x8 board.
        for band in range(42):
            base_y = int((band + 0.5) * height / 42)
            phase = rng.uniform(0, math.tau)
            amplitude = rng.uniform(1.5, 7.0)
            frequency = rng.uniform(0.0025, 0.009)
            drift = rng.uniform(-0.018, 0.018)
            points = []
            for x in range(0, width + 5, 5):
                y = base_y + math.sin(x * frequency + phase) * amplitude + x * drift
                points.append((x, max(0, min(height - 1, int(y)))))
            color = rng.choice(((77, 43, 27), (91, 53, 32), (111, 67, 41),
                                (35, 20, 14), (126, 77, 46)))
            pygame.draw.lines(surface, color, False, points, rng.choice((1, 1, 2)))
        # Large, irregular growth knots are placed on the board, not on every tile.
        for cx, cy, radius in ((width*.22, height*.31, width*.075),
                               (width*.73, height*.68, width*.095),
                               (width*.52, height*.14, width*.045)):
            for ring in range(4):
                rw = int(radius * (1.0 + ring*.34))
                rh = max(3, int(radius * .34 * (1.0 + ring*.34)))
                rect = pygame.Rect(0, 0, rw*2, rh*2)
                rect.center = (int(cx), int(cy))
                pygame.draw.ellipse(surface, (30 + ring*5, 17 + ring*4, 12 + ring*3), rect, 1)
        # Soft edge darkening makes the material read as one finished slab.
        pygame.draw.rect(surface, (20, 12, 9), (0, 0, width, height), max(2, width//100))
        self.material_cache[key] = surface
        return surface

    def _tile_sprite(self, light, size, variant=0, gradient_y=0.5):
        """Return a square surface for the selected theme.

        Default intentionally retains its v14 appearance. All selectable themes
        use clean, flat color fields except Abyss's board-wide color progression.
        """
        theme = self.settings.get("theme", "Default")
        key = (theme, light, size, variant, round(gradient_y, 4))
        if key in self.tile_cache:
            return self.tile_cache[key]

        if theme == "Default":
            # Preserve the existing Default material exactly as it appeared in v14.
            base = (76, 77, 82) if light else (23, 24, 29)
            edge = (139, 119, 88) if light else (66, 57, 49)
            tile = pygame.Surface((size, size))
            tile.fill(base)
            pygame.draw.rect(tile, shade_color(base, 10), (2, 2, size-4, size-4))
            pygame.draw.line(tile, shade_color(edge, 18), (1,1), (size-2,1), 1)
            pygame.draw.line(tile, shade_color(base, -28), (1,size-2), (size-2,size-2), 1)
            pygame.draw.line(tile, shade_color(edge, 5), (1,1), (1,size-2), 1)

        elif theme == "Wood":
            # Flat, uninterrupted alternating colors; no grain, lines or bevels.
            tile = pygame.Surface((size, size))
            tile.fill((0xBF, 0x89, 0x4B) if light else (0x7C, 0x41, 0x1F))

        elif theme == "Abyss":
            # Light squares stay solid navy. Dark squares sample one continuous
            # board-wide vertical gradient, so each square is a flat color and
            # the color changes gradually from the top of the board to bottom.
            tile = pygame.Surface((size, size))
            if light:
                tile.fill((0x03, 0x04, 0x5E))
            else:
                top = (0x02, 0x3E, 0x8A)
                bottom = (0x00, 0x96, 0xC8)
                t = max(0.0, min(1.0, gradient_y))
                color = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
                tile.fill(color)

        elif theme == "Royal":
            # Keep the existing Royal palette, removing the center medallions/decoration.
            tile = pygame.Surface((size, size))
            tile.fill((157, 143, 119) if light else (45, 28, 29))

        elif theme == "Empire":
            # Updated Empire palette: warm stone ivory and near-black.
            tile = pygame.Surface((size, size))
            tile.fill((0xDA, 0xD3, 0xC2) if light else (0x0C, 0x0B, 0x0D))

        else:
            tile = pygame.Surface((size, size))
            tile.fill((76, 77, 82) if light else (23, 24, 29))

        self.tile_cache[key] = tile
        return tile

    def draw_board_frame(self, board_rect):
        """Decorative multi-rail frame with corner hardware and engraved ticks."""
        theme = self.settings.get("theme", "Default")
        accents = {
            "Default": ((21,22,27), (153,126,83), (83,72,58)),
            "Wood": ((45,24,12), (191,137,75), (124,65,31)),
            "Royal": ((32,18,20), (190,157,99), (96,58,52)),
            "Abyss": ((3,4,40), (0,150,200), (2,62,138)),
            "Empire": ((12,11,13), (218,211,194), (82,73,85)),
        }
        dark, metal, inset = accents.get(theme, accents["Default"])
        outer = board_rect.inflate(34,34)
        pygame.draw.rect(self.screen, (5,5,7), outer, border_radius=5)
        pygame.draw.rect(self.screen, dark, outer.inflate(-4,-4), border_radius=4)
        pygame.draw.rect(self.screen, metal, outer, 2, border_radius=5)
        pygame.draw.rect(self.screen, inset, board_rect.inflate(12,12), 3, border_radius=2)
        pygame.draw.rect(self.screen, shade_color(metal, -35), board_rect.inflate(6,6), 1)
        # Corner plates and small rivets, like a crafted physical board.
        for x in (outer.left+9, outer.right-9):
            for y in (outer.top+9, outer.bottom-9):
                pygame.draw.circle(self.screen, metal, (x,y), 4)
                pygame.draw.circle(self.screen, (12,11,12), (x,y), 2)
        for i in range(8):
            px = board_rect.x + int((i+.5)*board_rect.width/8)
            py = board_rect.y + int((i+.5)*board_rect.height/8)
            pygame.draw.line(self.screen, metal, (px,outer.top+4), (px,outer.top+8), 1)
            pygame.draw.line(self.screen, metal, (px,outer.bottom-8), (px,outer.bottom-4), 1)
            pygame.draw.line(self.screen, metal, (outer.left+4,py), (outer.left+8,py), 1)
            pygame.draw.line(self.screen, metal, (outer.right-8,py), (outer.right-4,py), 1)

    def draw_board(self, board_rect):
        # Paint the frame/backing first. In v12 this was called at the end,
        # where its filled backing rectangle covered every square and piece.
        self.draw_board_frame(board_rect)
        flipped = self.mode == "ai" and self.player_color == C.BLACK
        sq = board_rect.width // 8
        for row in range(8):
            for col in range(8):
                sr, sc = (7-row, 7-col) if flipped else (row, col)
                r = pygame.Rect(board_rect.x+col*sq, board_rect.y+row*sq, sq, sq)
                light=(sr+sc)%2==0
                gradient_y = (row + 0.5) / 8.0
                self.screen.blit(self._tile_sprite(light, sq, (row * 3 + col * 5) % 4, gradient_y), r)
                actual_row, actual_col = (7-row, 7-col) if flipped else (row, col)
                square = (actual_row, actual_col)
                overlay_color = self.pending_end_highlights.get(square)
                if overlay_color is None:
                    overlay_color = self.current_check_highlights.get(square)
                if overlay_color is None:
                    overlay_color = self.legal_move_highlights.get(square)
                if overlay_color is not None:
                    overlay = pygame.Surface((sq, sq), pygame.SRCALPHA)
                    overlay.fill((*overlay_color, 155))
                    self.screen.blit(overlay, r)
                if self.last_move and (actual_row,actual_col) in (
                    (self.last_move.from_row,self.last_move.from_col),
                    (self.last_move.to_row,self.last_move.to_col)):
                    overlay=pygame.Surface((sq,sq),pygame.SRCALPHA)
                    overlay.fill((214,170,63,75)); self.screen.blit(overlay,r)
                if self.selected == (actual_row,actual_col):
                    pygame.draw.rect(self.screen,SELECT,r,4)
                for m in self.legal_moves:
                    if ((m.to_row,m.to_col)==(actual_row,actual_col)
                            and (actual_row, actual_col) not in self.legal_move_highlights):
                        pygame.draw.circle(self.screen,LEGAL,r.center,max(6,sq//9))
                piece=self.board.board[actual_row][actual_col]
                anim = self.move_animation
                is_anim_destination = bool(
                    anim and any((actual_row, actual_col) == actor["to"]
                                 for actor in anim["actors"])
                )
                if piece and not is_anim_destination:
                    inset=int(sq*.07)
                    self.draw_piece(piece,r.inflate(-inset*2,-inset*2))
                label_color=(229,213,183) if not light else (43,36,29)
                if col==0:
                    self.text(self.screen,str(8-sr),12,label_color,topleft=(r.x+4,r.y+2))
                if row==7:
                    self.text(self.screen,"abcdefgh"[sc],12,label_color,topleft=(r.right-14,r.bottom-16))
        # Draw special-move actors and captured-piece fade overlays.
        anim = self.move_animation
        if anim:
            anim_now = self.pause_started if self.pause_started is not None else time.monotonic()
            elapsed = anim_now - anim["started"]
            progress = min(1.0, max(0.0, elapsed / self.animation_duration))
            eased = progress * progress * (3.0 - 2.0 * progress)
            sprite_size = max(24, int(sq * .86))

            # A captured piece fades out while the moving piece arrives.
            captured = anim.get("captured")
            if captured:
                cap_rect = self.screen_square(*captured["square"], flipped, board_rect)
                cap_sprite = self._piece_sprite(captured["piece"], sprite_size).copy()
                cap_sprite.set_alpha(max(0, int(255 * (1.0 - progress))))
                self.screen.blit(cap_sprite, cap_sprite.get_rect(center=cap_rect.center))

            # Castling has two actors: the king and the rook.
            for actor in anim["actors"]:
                from_rect = self.screen_square(*actor["from"], flipped, board_rect)
                to_rect = self.screen_square(*actor["to"], flipped, board_rect)
                start = pygame.Vector2(from_rect.center)
                end = pygame.Vector2(to_rect.center)
                point = start.lerp(end, eased)
                sprite = self._piece_sprite(actor["piece"], sprite_size)
                shadow = pygame.Surface((sq, sq), pygame.SRCALPHA)
                pygame.draw.circle(shadow, (0, 0, 0, 75), (sq//2, sq//2), max(8, sq//3))
                self.screen.blit(shadow, (int(point.x-sq//2), int(point.y-sq//2+sq*.08)))
                self.screen.blit(sprite, sprite.get_rect(center=(round(point.x), round(point.y))))
            if progress >= 1.0:
                self.move_animation = None

    def _checking_pieces(self, attacker_color, king_square):
        """Return every piece square that currently attacks the given king square."""
        if king_square is None:
            return set()
        enemy = C.BLACK if attacker_color == C.WHITE else C.WHITE
        result = set()
        kr, kc = king_square
        for row in range(8):
            for col in range(8):
                piece = self.board.board[row][col]
                if not self.board._is_piece_of_color(piece, attacker_color):
                    continue
                if any(m.to_row == kr and m.to_col == kc
                       for m in self.board._pseudo_moves(row, col, attacker_color, enemy)):
                    result.add((row, col))
        return result

    def _classify_selected_moves(self, moves):
        """Preview captures only; check highlights appear after a move is played."""
        highlights = {}
        for move in moves:
            target = self.board.board[move.to_row][move.to_col]
            is_capture = target != C.EMPTY or (
                self.board.en_passant == (move.to_row, move.to_col)
                and self.board.board[move.from_row][move.from_col] in (C.WP, C.BP)
                and move.from_col != move.to_col
            )
            if is_capture:
                highlights[(move.to_row, move.to_col)] = CAPTURE_HIGHLIGHT
        return highlights, None

    def _start_end_sequence(self, status):
        """Keep the final board visible with result highlights for three seconds."""
        if self.pending_end_status is not None:
            return
        self.pending_end_status = status
        self.pending_end_started = time.monotonic()
        self.selected = None
        self.legal_moves = []
        self.legal_move_highlights = {}
        self.checking_king_square = None
        highlights = {}
        if status.state == "checkmate":
            loser = self.board.turn
            king_square = self.board._find_king(loser)
            winner = C.BLACK if loser == C.WHITE else C.WHITE
            for square in self._checking_pieces(winner, king_square):
                highlights[square] = CHECK_HIGHLIGHT
            if king_square != (-1, -1):
                highlights[king_square] = CAPTURE_HIGHLIGHT
            self.play_sound("checkmate")
        else:
            for color in (C.WHITE, C.BLACK):
                king_square = self.board._find_king(color)
                if king_square != (-1, -1):
                    highlights[king_square] = DRAW_HIGHLIGHT
            self.play_sound("checkmate")
        self.pending_end_highlights = highlights

    def format_move(self, move, piece):
        name = PIECE_LABEL.get(piece, "")
        capture = self.board.board[move.to_row][move.to_col] != C.EMPTY
        files = "abcdefgh"
        dest = f"{files[move.to_col]}{8-move.to_row}"
        if name == "P":
            prefix = files[move.from_col] if capture else ""
        else:
            prefix = name
        return f"{prefix}{'x' if capture else ''}{dest}"

    def make_move(self, move):
        piece = self.board.board[move.from_row][move.from_col]
        captured_piece = self.board.board[move.to_row][move.to_col]
        capture_square = (move.to_row, move.to_col)
        # En-passant captures a pawn on the square behind the destination.
        if (piece in (C.WP, C.BP) and captured_piece == C.EMPTY
                and self.board.en_passant == (move.to_row, move.to_col)
                and move.from_col != move.to_col):
            capture_square = (move.from_row, move.to_col)
            captured_piece = self.board.board[capture_square[0]][capture_square[1]]

        actors = [{
            "piece": piece,
            "from": (move.from_row, move.from_col),
            "to": (move.to_row, move.to_col),
        }]
        # In castling, animate the rook at the same time as the king.
        if piece in (C.WK, C.BK) and abs(move.to_col - move.from_col) == 2:
            rook_from_col, rook_to_col = ((7, 5) if move.to_col == 6 else (0, 3))
            actors.append({
                "piece": C.WR if piece == C.WK else C.BR,
                "from": (move.from_row, rook_from_col),
                "to": (move.from_row, rook_to_col),
            })

        notation = self.format_move(move, piece)
        self.move_animation = ({
            "actors": actors,
            "captured": ({"piece": captured_piece, "square": capture_square}
                         if captured_piece else None),
            "started": time.monotonic(),
        } if self.settings.get("animations", True) else None)
        if move.promotion:
            notation += "=" + PIECE_LABEL[move.promotion]
        self.board.push_move(move)
        self.last_move = move
        self.selected = None
        self.legal_moves = []
        self.legal_move_highlights = {}
        self.checking_king_square = None
        ply = len(self.move_text)
        side = C.WHITE if ply % 2 == 0 else C.BLACK
        if side == C.WHITE:
            notation = f"{ply // 2 + 1}.  {notation}"
        self.move_text.append((side, notation))
        status = self.board.get_status()
        self.current_check_highlights = {}
        self.checking_king_square = None
        if status.is_over:
            # End-state sound only: do not layer a normal move sound underneath it.
            self._start_end_sequence(status)
        else:
            if self.board._is_in_check(self.board.turn):
                checked_king = self.board._find_king(self.board.turn)
                attacker = C.BLACK if self.board.turn == C.WHITE else C.WHITE
                for square in self._checking_pieces(attacker, checked_king):
                    self.current_check_highlights[square] = CHECK_HIGHLIGHT
                if checked_king not in (None, (-1, -1)):
                    self.current_check_highlights[checked_king] = CHECK_HIGHLIGHT
                # A checking move plays only the check cue, never the move cue.
                self.play_sound("check")
            else:
                self.play_sound("move")
            # The move has completed; start the AI response immediately.
            self._maybe_start_ai()

    def finish_game(self, status):
        self.elapsed = time.monotonic() - self.start_time
        if status.state == "checkmate":
            self.winner_text = "WHITE WINS" if status.winner == C.WHITE else "BLACK WINS"
            self.end_reason = "CHECKMATE"
        else:
            self.winner_text = "DRAW"
            self.end_reason = "STALEMATE" if status.state == "stalemate" else "DRAW"
        self.state = "result"

    def draw_move_history(self, rect, max_rows=None):
        """Render one half-move per row with side-specific backgrounds and gold text."""
        pygame.draw.rect(self.screen, PANEL_2, rect, border_radius=5)
        self.history_view_rect = rect.copy()
        row_h = 30
        available = max(0, (rect.height - 12) // row_h)
        if max_rows is not None:
            available = min(available, max_rows)
        max_scroll = max(0, len(self.move_text) - available)
        self.history_scroll = max(0, min(self.history_scroll, max_scroll))
        end = len(self.move_text) - self.history_scroll
        start = max(0, end - available)
        entries = self.move_text[start:end] if available else []
        for index, (side, notation) in enumerate(entries):
            row = pygame.Rect(rect.x + 6, rect.y + 6 + index * row_h,
                              rect.width - 12, row_h - 3)
            if side == C.WHITE:
                bg = (218, 211, 194)
                gold_text = (139, 99, 43)
            else:
                bg = (12, 11, 13)
                gold_text = (211, 176, 105)
            pygame.draw.rect(self.screen, bg, row, border_radius=3)
            self.text(self.screen, notation, 15, gold_text,
                      topleft=(row.x + 9, row.y + 5), bold=True)

    def open_pause(self):
        if self.state == "game":
            self.pause_started = time.monotonic()
            self.pause_return_state = "game"
            self.state = "pause"
            self.selected = None
            self.legal_moves = []

    def resume_game(self):
        if self.pause_started is not None:
            # Exclude paused time from both the game clock and active animations.
            paused_for = time.monotonic() - self.pause_started
            self.start_time += paused_for
            if self.move_animation is not None:
                self.move_animation["started"] += paused_for
            self.pause_started = None
        self.state = "game"

    def draw_pause(self, mouse):
        # Dim the live board while keeping the game visible underneath.
        shade = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 185))
        self.screen.blit(shade, (0, 0))
        w, h = self.screen.get_size()
        panel = pygame.Rect(w // 2 - 225, h // 2 - 205, 450, 410)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=9)
        pygame.draw.rect(self.screen, GOLD, panel, 2, border_radius=9)
        self.text(self.screen, "PAUSED", 36, PALE_GOLD,
                  center=(panel.centerx, panel.y + 52), bold=True)
        labels = ["START", "REPLAY", "SETTINGS", "QUIT"]
        rects = []
        for i, label in enumerate(labels):
            rect = pygame.Rect(panel.x + 75, panel.y + 100 + i * 68, 300, 52)
            self.button(rect, label, rect.collidepoint(mouse), i == 0)
            rects.append(rect)
        self.pause_buttons = rects
        return rects

    def draw_game(self, mouse):
        self.screen.fill(BG)
        w,h = self.screen.get_size()
        board_size = min(h-100, w-430, 660)
        board_size = max(400, board_size)
        board_rect = pygame.Rect(42, (h-board_size)//2, board_size, board_size)
        self.draw_board(board_rect)
        panel = pygame.Rect(board_rect.right+35, 55, max(280,w-board_rect.right-70), h-110)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=8)
        pygame.draw.rect(self.screen, (76,65,55), panel, 1, border_radius=8)
        x = panel.x+22
        self.text(self.screen, "DARK FANTASY CHESS", 20, PALE_GOLD, topleft=(x,panel.y+20),bold=True)
        self.pause_button_rect = pygame.Rect(panel.right - 104, panel.y + 14, 82, 34)
        if self.state == "result_board":
            self.result_board_back_rect = pygame.Rect(panel.right - 190, panel.y + 14, 168, 34)
            self.button(self.result_board_back_rect, "BACK TO RESULT",
                        self.result_board_back_rect.collidepoint(mouse), False)
        elif self.pending_end_status is None:
            self.button(self.pause_button_rect, "PAUSE", self.pause_button_rect.collidepoint(mouse), False)
        else:
            label = "CHECKMATE" if self.pending_end_status.state == "checkmate" else "DRAW"
            self.text(self.screen, label, 17, PALE_GOLD, topleft=(panel.right - 150, panel.y + 20), bold=True)
        turn = "WHITE" if self.board.turn == C.WHITE else "BLACK"
        self.text(self.screen, f"{turn} TO MOVE", 18, TEXT, topleft=(x,panel.y+62))
        if self.board._is_in_check(self.board.turn):
            self.text(self.screen, "CHECK", 16, (220,83,77), topleft=(x,panel.y+88),bold=True)
        now = self.pause_started if self.pause_started is not None else time.monotonic()
        elapsed = now-self.start_time
        self.text(self.screen, f"TIME  {int(elapsed//60):02}:{int(elapsed%60):02}", 17, MUTED,
                  topleft=(x,panel.y+122))
        mode_label = "PLAYER VS AI" if self.mode == "ai" else "TWO PLAYERS"
        self.text(self.screen, mode_label, 15, MUTED, topleft=(x,panel.y+153))
        if self.mode == "ai":
            self.text(self.screen, f"DIFFICULTY  {self.difficulty.upper()}", 14, MUTED,
                      topleft=(x,panel.y+178))
        self.text(self.screen, "MOVE HISTORY", 17, PALE_GOLD, topleft=(x,panel.y+220),bold=True)
        history_rect = pygame.Rect(x,panel.y+250,panel.width-44,max(80,panel.height-325))
        self.draw_move_history(history_rect)
        if self.ai_thinking:
            self.text(self.screen, "AI THINKING...", 14, GOLD, topleft=(x,panel.bottom-42))
        elif self.ai_error:
            self.text(self.screen, "AI ERROR - SEE CONSOLE", 13, (220,83,77), topleft=(x,panel.bottom-42))
        return board_rect

    def draw_result(self, mouse):
        self.screen.fill(BG)
        w,h = self.screen.get_size()
        panel = pygame.Rect(w//2-310,h//2-300,620,600)
        pygame.draw.rect(self.screen,PANEL,panel,border_radius=8)
        pygame.draw.rect(self.screen,GOLD,panel,2,border_radius=8)
        self.text(self.screen,self.winner_text,40,PALE_GOLD,center=(w//2,panel.y+48),bold=True)
        self.text(self.screen,self.end_reason,16,RED,center=(w//2,panel.y+83),bold=True)
        mode_label = "Classic | Two Players" if self.mode=="two_players" else f"Classic | Vs AI ({self.difficulty})"
        self.text(self.screen,mode_label,16,MUTED,center=(w//2,panel.y+122))
        self.text(self.screen,f"GAME TIME  {int(self.elapsed//60):02}:{int(self.elapsed%60):02}",
                  17,TEXT,center=(w//2,panel.y+153))
        self.text(self.screen,"MOVE HISTORY",18,PALE_GOLD,center=(w//2,panel.y+194),bold=True)
        hist = pygame.Rect(panel.x+45,panel.y+218,panel.width-90,235)
        self.draw_move_history(hist, max_rows=7)
        button_y = panel.bottom - 105
        again = pygame.Rect(w//2-260,button_y,164,52)
        view = pygame.Rect(w//2-82,button_y,164,52)
        quit_rect = pygame.Rect(w//2+96,button_y,164,52)
        self.button(again,"PLAY AGAIN",again.collidepoint(mouse),False)
        self.button(view,"VIEW BOARD",view.collidepoint(mouse),False)
        self.button(quit_rect,"QUIT",quit_rect.collidepoint(mouse))
        return [again,view,quit_rect]

    def handle_board_click(self, pos, board_rect):
        if self.move_animation is not None or self.pending_end_status is not None:
            return
        flipped = self.mode == "ai" and self.player_color == C.BLACK
        square = self.square_at(pos, board_rect, flipped)
        if square is None or (self.mode=="ai" and self.board.turn != self.player_color):
            self.selected = None
            self.legal_moves = []
            self.legal_move_highlights = {}
            self.checking_king_square = None
            return
        r,c = square
        piece = self.board.board[r][c]
        if self.selected is not None:
            candidates = [m for m in self.legal_moves if (m.to_row,m.to_col)==square]
            if candidates:
                promotions = [m for m in candidates if m.promotion]
                if promotions:
                    self.pending_promotion = promotions
                else:
                    self.make_move(candidates[0])
                return
        if piece and self.board._is_piece_of_color(piece,self.board.turn):
            self.selected = square
            self.legal_moves = [m for m in self.board.generate_legal_moves()
                                if (m.from_row,m.from_col)==square]
            self.legal_move_highlights, self.checking_king_square = self._classify_selected_moves(self.legal_moves)
        else:
            self.selected = None
            self.legal_moves = []
            self.legal_move_highlights = {}
            self.checking_king_square = None

    def run(self):
        running = True
        board_rect = None
        while running:
            mouse = pygame.mouse.get_pos()
            self.clock.tick(FPS)
            if self.state == "menu":
                buttons = self.draw_menu(mouse)
            elif self.state == "settings":
                buttons = self.draw_settings(mouse)
            elif self.state == "choose_mode":
                buttons = self.draw_choice("CHOOSE GAME TYPE",["TWO PLAYERS","VS AI","BACK"],
                                            mouse, horizontal_count=2)
            elif self.state == "difficulty":
                buttons = self.draw_choice("CHOOSE DIFFICULTY",["EASY","NORMAL","HARD","BACK"],mouse)
            elif self.state == "game_mode":
                buttons = self.draw_choice("GAME MODE",["CLASSIC","BACK"],mouse,
                                           "Standard chess · No time limit")
            elif self.state == "color":
                buttons = self.draw_choice("CHOOSE YOUR SIDE",["WHITE","BLACK","RANDOM","BACK"],
                                            mouse, horizontal_count=3)
            elif self.state == "game":
                board_rect = self.draw_game(mouse)
                buttons = []
                if self.pending_promotion:
                    overlay = pygame.Rect(self.screen.get_width()//2-210, self.screen.get_height()//2-80,420,160)
                    pygame.draw.rect(self.screen,PANEL,overlay,border_radius=8)
                    pygame.draw.rect(self.screen,GOLD,overlay,2,border_radius=8)
                    self.text(self.screen,"PROMOTE PAWN",20,PALE_GOLD,center=(overlay.centerx,overlay.y+30))
                    for i,(label,ptype) in enumerate(PROMOTIONS):
                        r = pygame.Rect(overlay.x+15+i*101,overlay.y+65,92,55)
                        self.button(r,label,r.collidepoint(mouse),False)
                        buttons.append((r,ptype))
            elif self.state == "pause":
                # Draw the frozen game first, then place the pause dialog over it.
                board_rect = self.draw_game(mouse)
                buttons = self.draw_pause(mouse)
            elif self.state == "result":
                buttons = self.draw_result(mouse)
            elif self.state == "result_board":
                board_rect = self.draw_game(mouse)
                buttons = []
            else:
                buttons = []
            pygame.display.flip()

            # Apply completed AI move on the main thread.
            if (self.state == "game" and self.pending_end_status is None
                    and self.move_animation is None
                    and self.ai_result is not None and not self.ai_thinking):
                result = self.ai_result
                self.ai_result = None
                if isinstance(result, Exception):
                    self.ai_thinking = False
                    self.ai_error = str(result)
                    print(f"AI search failed: {result!r}")
                elif result is not None:
                    self.ai_error = None
                    self.make_move(result)
                else:
                    self.ai_error = "AI returned no legal move"

            if (self.state == "game" and self.pending_end_status is not None
                    and self.pending_end_started is not None
                    and time.monotonic() - self.pending_end_started >= 3.0):
                self.finish_game(self.pending_end_status)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if self.state == "game":
                        if self.pending_end_status is None:
                            self.open_pause()
                    elif self.state == "pause":
                        self.resume_game()
                    elif self.state == "result_board":
                        self.state = "result"
                    elif self.state == "settings" and self.pause_return_state == "pause":
                        self.theme_dropdown_open = False
                        self.state = "pause"
                    elif self.state != "menu":
                        self.theme_dropdown_open = False
                        self.state = "menu"
                elif event.type == pygame.MOUSEWHEEL:
                    if (self.state in ("game", "result") and self.history_view_rect
                            and self.history_view_rect.collidepoint(mouse)):
                        self.history_scroll = max(0, self.history_scroll - event.y * 2)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    pos = event.pos
                    if self.state == "menu":
                        if buttons[0].collidepoint(pos): self.state = "choose_mode"
                        elif buttons[1].collidepoint(pos):
                            self.pause_return_state = "menu"
                            self.state = "settings"
                        elif buttons[2].collidepoint(pos): running = False
                    elif self.state == "settings":
                        if self.settings_controls.get("back") and self.settings_controls["back"].collidepoint(pos):
                            self.theme_dropdown_open = False
                            self.state = "pause" if self.pause_return_state == "pause" else "menu"
                        else:
                            # Dropdown options take priority over every underlying row.
                            chosen_theme = False
                            if self.theme_dropdown_open:
                                for i, theme in enumerate(self.theme_options):
                                    rect = self.settings_controls.get(f"theme_{i}")
                                    if rect and rect.collidepoint(pos):
                                        self.settings["theme"] = theme
                                        self.theme_dropdown_open = False
                                        self.tile_cache.clear()
                                        self.save_settings()
                                        chosen_theme = True
                                        break
                            if not chosen_theme:
                                if self.theme_dropdown_open:
                                    # Consume clicks outside the popup; never let them activate
                                    # the Fullscreen row underneath/near the dropdown.
                                    self.theme_dropdown_open = False
                                elif self.settings_controls.get("sound") and self.settings_controls["sound"].collidepoint(pos):
                                    self.settings["sound"] = not self.settings["sound"]
                                    self.save_settings()
                                elif self.settings_controls.get("animations") and self.settings_controls["animations"].collidepoint(pos):
                                    self.settings["animations"] = not self.settings["animations"]
                                    self.save_settings()
                                elif self.settings_controls.get("theme") and self.settings_controls["theme"].collidepoint(pos):
                                    self.theme_dropdown_open = True
                                elif self.settings_controls.get("fullscreen") and self.settings_controls["fullscreen"].collidepoint(pos):
                                    self.toggle_fullscreen()
                    elif self.state == "choose_mode":
                        if buttons[0].collidepoint(pos): self.mode="two_players"; self.state="game_mode"
                        elif buttons[1].collidepoint(pos): self.mode="ai"; self.state="difficulty"
                        elif buttons[2].collidepoint(pos): self.state="menu"
                    elif self.state == "difficulty":
                        if buttons[0].collidepoint(pos): self.difficulty="easy"; self.state="game_mode"
                        elif buttons[1].collidepoint(pos): self.difficulty="normal"; self.state="game_mode"
                        elif buttons[2].collidepoint(pos): self.difficulty="hard"; self.state="game_mode"
                        elif buttons[3].collidepoint(pos): self.state="choose_mode"
                    elif self.state == "game_mode":
                        if buttons[0].collidepoint(pos): self.state="color"
                        elif buttons[1].collidepoint(pos): self.state="difficulty" if self.mode=="ai" else "choose_mode"
                    elif self.state == "color":
                        if buttons[0].collidepoint(pos): self.begin_game(C.WHITE)
                        elif buttons[1].collidepoint(pos): self.begin_game(C.BLACK)
                        elif buttons[2].collidepoint(pos): self.begin_game(random.choice([C.WHITE,C.BLACK]))
                        elif buttons[3].collidepoint(pos): self.state="game_mode"
                    elif self.state == "pause":
                        if buttons[0].collidepoint(pos):
                            self.resume_game()
                        elif buttons[1].collidepoint(pos):
                            self.begin_game(self.player_color)
                        elif buttons[2].collidepoint(pos):
                            self.pause_return_state = "pause"
                            self.state = "settings"
                        elif buttons[3].collidepoint(pos):
                            self.pause_started = None
                            self.state = "menu"
                    elif self.state == "game":
                        if self.pending_end_status is not None:
                            continue
                        if self.pause_button_rect and self.pause_button_rect.collidepoint(pos):
                            self.open_pause()
                        elif self.pending_promotion:
                            for rect,ptype in buttons:
                                if rect.collidepoint(pos):
                                    chosen = next((m for m in self.pending_promotion
                                                   if C.piece_type(m.promotion)==ptype),None)
                                    self.pending_promotion=None
                                    if chosen: self.make_move(chosen)
                                    break
                        elif board_rect:
                            self.handle_board_click(pos,board_rect)
                    elif self.state == "result":
                        if buttons[0].collidepoint(pos): self.begin_game(self.player_color)
                        elif buttons[1].collidepoint(pos): self.state="result_board"
                        elif buttons[2].collidepoint(pos): self.state="menu"
                    elif self.state == "result_board":
                        if self.result_board_back_rect and self.result_board_back_rect.collidepoint(pos):
                            self.state = "result"
        pygame.quit()
        return 0


if __name__ == "__main__":
    raise SystemExit(DarkFantasyChess().run())
