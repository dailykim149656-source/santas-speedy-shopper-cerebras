#!/usr/bin/env python3
"""Private gift8 film watcher, independent of the score-first sender.

Start before the campaign: python3 tools/gift8_film.py --start 5051
Inspect saved clips: python3 tools/gift8_film.py --inspect 5051
Capture an additional attempt: python3 tools/gift8_film.py --retry 5051

The controller writes CACHE/recording-complete-gift8-5051 only after all
sends have stopped. Clips remain in CACHE/film-gift8-5051, including partial
and below-threshold recordings. A retry after completion is a post-run clip;
it cannot establish full-run coverage. This watcher never sends model requests
or delays the sender. A matching .session.json is required before recording.
"""
import importlib.util
from pathlib import Path


# Load a separate module instance so importing this adapter cannot reconfigure
# another caller's first5027 watcher in the same interpreter.
_spec = importlib.util.spec_from_file_location(
    '_gift8_film_runtime', Path(__file__).with_name('first5027_film.py'))
film = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(film)
film.__doc__ = __doc__
film.START = 5051
film.VARIANTS = {'gift8-tool', 'gift8-prefetch'}
film.FILMS = film.CACHE / 'film-gift8-5051'
film.SENTINEL = film.CACHE / 'recording-complete-gift8-5051'


def __getattr__(name):
    return getattr(film, name)


if __name__ == '__main__':
    film.main()
