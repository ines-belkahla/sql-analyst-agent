"""STEP 0 - Keep only our 3 databases from the full BIRD Mini-Dev download.

Before: extract the BIRD Mini-Dev package anywhere inside data/download/
Run:    python -m data_engineering.select_subset
After:  data/raw/<db>/<db>.sqlite, data/raw/<db>/database_description/*.csv,
        data/raw/questions.json (only the questions of our 3 databases)
"""
import json
import shutil
import zipfile

from data_engineering.config import DATABASES, DOWNLOAD_DIR, RAW_DIR


def find(pattern):
    """First match under data/download/, ignoring macOS junk folders."""
    for path in sorted(DOWNLOAD_DIR.rglob(pattern)):
        if "__MACOSX" not in path.parts:
            return path
    return None


def main():
    # The databases sometimes come as a zip inside the package: extract it
    if find("dev_databases") is None:
        for archive in DOWNLOAD_DIR.rglob("*.zip"):
            if "__MACOSX" not in archive.parts:
                print(f"Extracting {archive.name} ...")
                with zipfile.ZipFile(archive) as z:
                    z.extractall(archive.parent)

    databases_dir = find("dev_databases")
    questions_file = find("mini_dev_sqlite.json")
    if databases_dir is None or questions_file is None:
        raise SystemExit("BIRD Mini-Dev not found in data/download/. See README, step 4.")

    # Show every database so the choice can be checked with real numbers
    questions = json.loads(questions_file.read_text(encoding="utf-8"))
    print(f"{'database':<26}{'size (MB)':>10}{'questions':>11}")
    for folder in sorted(p for p in databases_dir.iterdir() if p.is_dir()):
        sqlite = folder / f"{folder.name}.sqlite"
        if sqlite.exists():
            size = sqlite.stat().st_size / 1e6
            n = sum(q["db_id"] == folder.name for q in questions)
            mark = "  <- kept" if folder.name in DATABASES else ""
            print(f"{folder.name:<26}{size:>10.1f}{n:>11}{mark}")

    # Copy our databases and their questions to data/raw/
    shutil.rmtree(RAW_DIR, ignore_errors=True)
    for db_id in DATABASES:
        source = databases_dir / db_id
        target = RAW_DIR / db_id
        target.mkdir(parents=True)
        shutil.copy2(source / f"{db_id}.sqlite", target)
        shutil.copytree(source / "database_description", target / "database_description")

    kept = [q for q in questions if q["db_id"] in DATABASES]
    (RAW_DIR / "questions.json").write_text(json.dumps(kept, indent=2), encoding="utf-8")
    print(f"\nKept {len(DATABASES)} databases and {len(kept)} questions in {RAW_DIR}")


if __name__ == "__main__":
    main()
