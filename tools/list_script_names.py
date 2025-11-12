import json
import os

INPUT_JSON = "analysis_results.json"

POSSIBLE_KEYS = [
    "剧本名",
    "title",
    "name",
    "script_name",
    "doc_name",
    "文件名",
    "剧本",
    "剧本名称",
]

def extract_names(record):
    for k in POSSIBLE_KEYS:
        if k in record and record[k]:
            return str(record[k])
    for k in ("file_path", "path", "filename"):
        if k in record and record[k]:
            base = os.path.basename(record[k])
            return os.path.splitext(base)[0]
    return None

def main():
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = []
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        for key in ("results", "items", "data"):
            if key in data and isinstance(data[key], list):
                records = data[key]
                break

    names = []
    for rec in records:
        n = extract_names(rec)
        if n:
            names.append(n)

    # 去重，保留顺序
    seen = set()
    ordered = []
    for n in names:
        if n not in seen:
            ordered.append(n)
            seen.add(n)

    for n in ordered:
        print(n)
    print(f"__COUNT__={len(ordered)}")

if __name__ == "__main__":
    main()