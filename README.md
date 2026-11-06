<<<<<<< HEAD
# Dark Fantasy Chess — v19

## Run
From the project root:

```powershell
python src/main.py
```

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
=======
# Dark-fantasy-chess
A 2D Dark Fantasy Chess game built with Python and Pygame, featuring AI opponents, custom chess pieces, multiple board themes, animations, sound effects, and a complete chess gameplay experience.
>>>>>>> f904ba8a9e2ce47a91ad8ab35c30c9758a1d8dca
