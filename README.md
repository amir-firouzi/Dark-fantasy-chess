# Dark Fantasy Chess — v19

## Run
From the project root:

```powershell
python src/main.py
```

## v19 changes
- Legal capture destinations are highlighted red when a piece is selected; ordinary legal destinations retain green dots.
- Moves that give check are highlighted purple, along with the checked king's square.
- Checkmate displays the attacking piece square(s) in purple and the mated king square in red for three seconds before the result screen.
- Draw highlights both kings green, plays the checkmate sound effect, and transitions to the result screen after three seconds.
- Added a `VIEW BOARD` option to the result screen to inspect the final position.
- Added `.gitignore`; Windows EXE/BAT packaging work is excluded from this project stage.

## v17 changes
- Removed the Bedrock theme completely from the theme selector and valid saved settings.
- Updated Empire squares to flat `#DAD3C2` and `#0C0B0D`.

## Previous v16 changes
- Repetition of any position no longer causes an automatic draw. Other chess end conditions, including checkmate, stalemate, and the 50-move rule, remain active.
- Default theme is unchanged.
- Wood uses flat `#BF894B` and `#7C411F` squares.
- Abyss uses solid `#03045E` on the first square color. The second square color samples one continuous top-to-bottom board gradient from `#023E8A` to `#0096C8`; each individual square remains a flat color.
- Royal retains its existing colors, with no central circles.
- Empire previously used alternating `#FCF9F6` and `#343039` squares.
- Existing board frame geometry and sound effects are preserved.

## Tests
Run:

```powershell
python -m pytest -q
```

## v20 changes
- Selecting a piece previews legal captures in red and ordinary legal destinations in green only; it no longer previews purple check highlights.
- Purple highlights are applied only after a checking move is actually played, marking the checking piece(s) and the checked king.
- A checking move plays only the check sound. A normal move sound is played only when the move does not give check.
- Checkmate and draw continue to play only the checkmate sound, without an overlapping move sound.
