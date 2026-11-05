"""Step 1: download and clean the BIRD Mini-Dev dataset.

Run:  python -m src.download_data   (or: dvc repro download)

Output (data/bird/):
    databases/<db_id>/<db_id>.sqlite   the 11 SQLite databases
    questions.json                     the 500 questions with their reference SQL
    descriptions.csv                   ALL column descriptions, cleaned, in one UTF-8 file

If the Google Drive download fails, download the zip yourself from
https://github.com/bird-bench/mini_dev, save it as data/minidev.zip and run again.
"""

import csv
import io
import json
import shutil
import zipfile

import gdown

from src.config import BIRD_DIR, DATA_DIR, DATABASES_DIR, DESCRIPTIONS_FILE, QUESTIONS_FILE

GOOGLE_DRIVE_ID = "13VLWIwpw5E3d5DUkMvzw7hvHE67a4XkG"  # official "complete package" link
ZIP_PATH = DATA_DIR / "minidev.zip"
RAW_DIR = DATA_DIR / "raw"


def download():
    if ZIP_PATH.exists():
        print(f"Using existing {ZIP_PATH}")
        return
    DATA_DIR.mkdir(exist_ok=True)
    print("Downloading BIRD Mini-Dev from Google Drive...")
    gdown.download(id=GOOGLE_DRIVE_ID, output=str(ZIP_PATH), quiet=False)


def extract():
    """Unzip the package, then any zip inside it (the databases come as a nested zip)."""
    shutil.rmtree(RAW_DIR, ignore_errors=True)
    with zipfile.ZipFile(ZIP_PATH) as z:
        z.extractall(RAW_DIR)
    for inner in list(RAW_DIR.rglob("*.zip")):
        with zipfile.ZipFile(inner) as z:
            z.extractall(inner.parent)


def read_csv_any_encoding(path):
    """The BIRD CSV files use different encodings: try them one by one."""
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue


def clean(text):
    """Remove extra spaces and 'nan' values."""
    text = " ".join((text or "").split())
    return "" if text.lower() in ("nan", "none", "null") else text


def organize():
    questions_file = next(RAW_DIR.rglob("mini_dev_sqlite.json"))
    questions = json.loads(questions_file.read_text(encoding="utf-8"))
    db_ids = sorted({q["db_id"] for q in questions})

    # 1. Databases: keep only <db_id>/<db_id>.sqlite + its description CSVs
    shutil.rmtree(BIRD_DIR, ignore_errors=True)
    DATABASES_DIR.mkdir(parents=True)
    descriptions = []
    for db_id in db_ids:
        sqlite_file = next(
            p for p in RAW_DIR.rglob(f"{db_id}.sqlite") if "__MACOSX" not in p.parts
        )
        target = DATABASES_DIR / db_id
        target.mkdir()
        shutil.copy2(sqlite_file, target / sqlite_file.name)

        # 2. Descriptions: read every CSV, clean it, collect it in one list
        for csv_file in sorted((sqlite_file.parent / "database_description").glob("*.csv")):
            reader = csv.DictReader(io.StringIO(read_csv_any_encoding(csv_file)))
            reader.fieldnames = [clean(name).lower() for name in reader.fieldnames]
            for row in reader:
                column = clean(row.get("original_column_name"))
                if column:
                    descriptions.append({
                        "db_id": db_id,
                        "table": csv_file.stem.strip(),
                        "column": column,
                        "column_name": clean(row.get("column_name")),
                        "description": clean(row.get("column_description")),
                        "value_description": clean(row.get("value_description")),
                        "source": f"{db_id}/database_description/{csv_file.name}",
                    })

    with DESCRIPTIONS_FILE.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(descriptions[0]))
        writer.writeheader()
        writer.writerows(descriptions)

    # 3. Questions: keep the fields we use
    keep = ["question_id", "db_id", "question", "evidence", "SQL", "difficulty"]
    clean_questions = [{k: q.get(k, "") for k in keep} for q in questions]
    QUESTIONS_FILE.write_text(json.dumps(clean_questions, indent=2), encoding="utf-8")

    shutil.rmtree(RAW_DIR, ignore_errors=True)
    print(f"{len(db_ids)} databases, {len(clean_questions)} questions, "
          f"{len(descriptions)} column descriptions saved in {BIRD_DIR}")


if __name__ == "__main__":
    download()
    extract()
    organize()
