"""Browser entry point.  pygbag (pygame for WebAssembly) looks for main.py and runs it.

pygbag decides which libraries to load by reading the imports in THIS file,
so pygame must be imported here even though the game code imports it too.
On the desktop, `python hyperplane_heist.py` (or this file) starts the same game.
"""
import asyncio

import pygame  # noqa: F401  (tells pygbag to load pygame)

from heist.app import main_async

asyncio.run(main_async())
