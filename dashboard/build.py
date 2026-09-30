#!/usr/bin/env python3
"""Build dashboard/index.html from prospects.csv + dashboard/template.html.
Run from anywhere: python3 dashboard/build.py"""
import csv, json, datetime, pathlib
root = pathlib.Path(__file__).resolve().parent.parent
rows = list(csv.DictReader(open(root / "prospects.csv", newline="")))
tpl = (root / "dashboard" / "template.html").read_text()
data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
out = tpl.replace("__DATA__", data).replace("__BUILT__", datetime.date.today().isoformat())
(root / "dashboard" / "index.html").write_text(out)
print(f"built dashboard/index.html with {len(rows)} prospects")
