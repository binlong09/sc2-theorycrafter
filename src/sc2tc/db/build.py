"""CLI: build the unit_stats SQLite DB from seed datasets.

    python -m sc2tc.db.build
"""

from . import build, DEFAULT_DB_PATH


def main():
    path, n = build()
    print(f"Built {path} with {n} unit rows across all patch eras.")


if __name__ == "__main__":
    main()
