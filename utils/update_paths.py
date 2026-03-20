"""
update_paths.py — Find and replace old data path across all project files.
Run from: C:\Projects\trading_engine\

What it does:
- Scans every file in the trading_engine directory
- Replaces old path with new path
- Skips binary files, .git folder, and __pycache__
- Prints every file changed and every line changed
- Does a dry run first — no changes made until you confirm
"""

import os
import sys

OLD_PATH = r'C:\Projects\trading_engine\data\Historical Daily Data'
NEW_PATH = r'C:\Projects\trading_engine\data\Historical Daily Data'

# File extensions to scan
SCAN_EXTENSIONS = {'.py', '.yaml', '.yml', '.json', '.txt', '.cfg', '.ini', '.md', '.bat', '.csv'}

# Directories to skip
SKIP_DIRS = {'.git', '__pycache__', '.pytest_cache', 'node_modules', '.venv', 'venv'}

ROOT_DIR = r'C:\Projects\trading_engine'


def scan_and_replace(dry_run=True):
    changes = []

    for dirpath, dirnames, filenames in os.walk(ROOT_DIR):
        # Skip unwanted directories
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in SCAN_EXTENSIONS:
                continue

            filepath = os.path.join(dirpath, filename)

            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception as e:
                print(f"  SKIP (read error): {filepath} — {e}")
                continue

            if OLD_PATH not in content:
                continue

            # Count and show changes
            lines = content.split('\n')
            changed_lines = []
            for i, line in enumerate(lines, 1):
                if OLD_PATH in line:
                    changed_lines.append((i, line.strip()))

            changes.append({
                'filepath'     : filepath,
                'changed_lines': changed_lines,
                'new_content'  : content.replace(OLD_PATH, NEW_PATH)
            })

            rel_path = os.path.relpath(filepath, ROOT_DIR)
            print(f"\n  FILE: {rel_path}")
            for lineno, line in changed_lines:
                print(f"    Line {lineno:>4}: {line[:120]}")

    print(f"\n{'='*60}")
    print(f"  Total files to change: {len(changes)}")
    print(f"  Old path: {OLD_PATH}")
    print(f"  New path: {NEW_PATH}")
    print(f"{'='*60}")

    if not changes:
        print("  No files found with the old path. Nothing to do.")
        return

    if dry_run:
        print("\n  DRY RUN — no files were modified.")
        print("  Run with --apply to make changes.")
        return

    # Apply changes
    print("\n  Applying changes...")
    for change in changes:
        try:
            with open(change['filepath'], 'w', encoding='utf-8') as f:
                f.write(change['new_content'])
            rel_path = os.path.relpath(change['filepath'], ROOT_DIR)
            print(f"  UPDATED: {rel_path}")
        except Exception as e:
            print(f"  ERROR updating {change['filepath']}: {e}")

    print(f"\n  Done. {len(changes)} files updated.")
    print("  Run your sanity checks before committing to git.")


if __name__ == "__main__":
    dry_run = '--apply' not in sys.argv

    if dry_run:
        print("=" * 60)
        print("  PATH UPDATE — DRY RUN (preview only)")
        print("=" * 60)
    else:
        print("=" * 60)
        print("  PATH UPDATE — APPLYING CHANGES")
        print("=" * 60)

    scan_and_replace(dry_run=dry_run)