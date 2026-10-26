# Check every file extract.py reads against OPM's own copy: same version, current at OPM, identical bytes (SHA-256).
# python3 verify_opm.py  ->  data/opm_check.csv, which build.py reports in facts.md
# HuggingFace stores each file's SHA-256; OPM's files (data.opm.gov API) are streamed and hashed, not saved.
# The employment files are large (about 2 GB in all), so this takes a while.
import csv, datetime, hashlib, json, re, time, urllib.request
from pathlib import Path
from config import FIRST, MONTHLY_FROM

HF = "impactproject/opm-ehri-data"
OPM = "https://data.opm.gov/api/v1/files"


def get(url, attempts=6):
    for a in range(1, attempts + 1):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "federal-attrition-patterns"}), timeout=300)
        except Exception as e:
            if a == attempts:
                raise
            print(f"  {url}: {e} - retry {a}", flush=True)
            time.sleep(15 * a)


def hf_files(ds):
    """{yyyymm: (version, sha256)} for the newest version of each month on HuggingFace."""
    url, best = f"https://huggingface.co/api/datasets/{HF}/tree/main/{ds}?limit=1000", {}
    while url:
        r = get(url)
        for e in json.load(r):
            m = re.search(rf"{ds}_(\d{{6}})_v(\d+)\.parquet$", e["path"])
            if m and (m.group(1) not in best or int(m.group(2)) > best[m.group(1)][0]):
                best[m.group(1)] = (int(m.group(2)), e["lfs"]["oid"])
        n = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link", ""))
        url = n.group(1) if n else None
    return best


rows, checked = [], datetime.date.today().isoformat()
for ds in ("separations", "accessions", "employment"):
    hf = hf_files(ds)
    latest = max(hf)
    used = [ym for ym in hf if FIRST <= ym <= latest and (ds != "employment" or ym.endswith("01") or ym >= MONTHLY_FROM)]
    opm = {(x["year"] + x["month"], x["version"]): x["current"] for x in json.load(get(f"{OPM}/{ds}"))}
    for i, ym in enumerate(used, 1):
        v, hf_sha = hf[ym]
        current = max(ver for (m, ver), cur in opm.items() if m == ym and cur) if any(m == ym and c for (m, _), c in opm.items()) else None
        h = hashlib.sha256()
        if (ym, v) in opm:
            r = get(f"{OPM}/{ds}/{ym[:4]}/{ym[4:]}/{v}/download")
            while chunk := r.read(1 << 20):
                h.update(chunk)
        opm_sha = h.hexdigest() if (ym, v) in opm else ""
        rows.append({"dataset": ds, "file": ym, "hf_version": v, "opm_current_version": current, "hf_sha256": hf_sha,
                     "opm_sha256": opm_sha, "match": opm_sha == hf_sha and current == v, "checked": checked})
        print(f"{ds} {i}/{len(used)} {ym} v{v} opm current v{current} {'ok' if rows[-1]['match'] else 'MISMATCH'}", flush=True)
        time.sleep(0.5)

with open(Path("data") / "opm_check.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(sum(r["match"] for r in rows), "of", len(rows), "files match OPM")
