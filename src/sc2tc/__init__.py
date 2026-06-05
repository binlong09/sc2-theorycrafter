"""SC2 Theorycrafter — verified, patch-accurate StarCraft 2 game data + calculators.

Core principle: facts live in the database, reasoning lives in the model.
No unit stat is ever recalled from a model's weights — it comes from the DB,
tagged to a patch_era so we can answer "zealot stats for 5.0.16" vs "5.0.15".
"""

__version__ = "0.1.0"
