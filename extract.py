# Pull everything build.py needs: OPM EHRI from its HuggingFace mirror (newest version of each monthly file), plus the
# outside documents the facts quote (data/sources/).
# python3 extract.py  ->  data/sep.parquet, emp.parquet, hc.parquet, acc.parquet, rookie_*.parquet, *_ice_cbp.parquet,
#                         versions.parquet, age_*.parquet, asis_*.parquet, sources/
# One small aggregate per source file goes to data/cache/ first, so a rerun skips files it already has
# (HuggingFace rate-limits; a first run makes a few thousand reads and takes hours).
# age_*.parquet: age bracket by whole years of service (los_y, rounded down, from the leave service date: build.py treats MAX_LOS+ as not
# reported), for retirement eligibility and young hires.
import json, re, sys, time, urllib.request
from pathlib import Path
import duckdb

HF = "impactproject/opm-ehri-data"
BASE = f"https://huggingface.co/datasets/{HF}/resolve/main"
DATA, CACHE = Path("data"), Path("data/cache")
CACHE.mkdir(parents=True, exist_ok=True)
from config import PERM, SCD_TOL, MAX_LOS, LOS_CUTS, BAND_CUTS, NEW_HIRE_LOS, FIRST, MONTHLY_FROM, ICE_FROM, ROOKIE_FROM, USAJOBS_FROM, SOURCES, USAJOBS
# Years of service come from the leave service date (service_computation_date_leave), not OPM's length_of_service_years.
# OPM defines length of service as federal civilian service plus creditable military and other service, and from the
# March 2026 files on length_of_service_years equals the time since that date for every record. Before (February 2026
# is in between) it often left military time out (for veterans it matched the date in about a third of records),
# undocumented. Computing it from the date in every file puts all years on one definition, military time included.
# Measured at mid-month: the action's effective month for hires and departures, the snapshot month for staff.
EFF_DAY = "try_strptime(personnel_action_effective_date_yyyymm || '15', '%Y%m%d')::DATE"
SCD = "try_cast(service_computation_date_leave AS DATE)"
svc = lambda day: f"(datediff('day', {SCD}, {day}) / 365.25)"
SVC = svc(EFF_DAY)
# Service bands, as in fed-attrition-2026: years of service at the action (separations) or snapshot (headcount).
_c, _k = LOS_CUTS, "abcdef"
los = lambda y: (f"CASE WHEN {y} IS NULL OR {y} >= {MAX_LOS} THEN 'NA' "
                 + " ".join(f"WHEN {y} < {c} THEN '{_k[i]}{'<' if i == 0 else f'{_c[i - 1]}-'}{c}'" for i, c in enumerate(_c))
                 + f" ELSE '{_k[len(_c)]}{_c[-1]}+' END")
los_y = lambda y: f"CAST(floor({y}) AS INT)"
LOS, LOS_Y = los(SVC), los_y(SVC)
ICE_COLS = """agency_subelement_code AS agy_code, agency_subelement AS agency, {cat}
    pay_plan, pay_plan_code, occupational_series, occupational_series_code, occupational_category,
    grade, age_bracket, {svc} service_years, veteran_indicator, work_schedule, count::INT AS count,
    personnel_action_effective_date_yyyymm AS event_ym, '{ym}' AS file_ym"""


def versions(ds):
    """{yyyymm: {version: path}} for every file OPM has published, superseded versions included."""
    url, out = f"https://huggingface.co/api/datasets/{HF}/tree/main/{ds}?limit=1000", {}
    while url:
        with urllib.request.urlopen(url) as r:
            for e in json.load(r):
                m = re.search(rf"{ds}_(\d{{6}})_v(\d+)\.parquet$", e["path"])
                if m:
                    out.setdefault(m.group(1), {})[int(m.group(2))] = e["path"]
            n = re.search(r'<([^>]+)>;\s*rel="next"', r.headers.get("Link", ""))
            url = n.group(1) if n else None
    return dict(sorted(out.items()))


ALL = {ds: versions(ds) for ds in ("separations", "employment", "accessions")}
# The newest version of each month. The version is part of every cache name, so a republished month is read again.
FILES = {ds: {ym: (max(vs), vs[max(vs)]) for ym, vs in d.items()} for ds, d in ALL.items()}
LATEST = max(FILES["separations"])
print("newest file:", LATEST, flush=True)
# Every rate is per 1,000 January staff; OPM's January staff files start in 2012 (config.py holds FIRST to that).
START = FIRST
assert START in FILES["employment"], (START, "no January staff file")


def plan():
    """(cache name, select) for every source file."""
    for ym, (v, p) in FILES["separations"].items():
        if ym >= START:
            yield f"sep4_{ym}_v{v}", f"""SELECT '{ym}' file, personnel_action_effective_date_yyyymm eff, separation_category_code cat,
                drp_indicator drp, agency_code, agency_subelement_code, occupational_series_code, {LOS} los,
                appointment_type_code appt, education_level_bracket edu, sum(count::INT) n
                FROM '{BASE}/{p}' GROUP BY ALL"""
            yield f"agesep2_{ym}_v{v}", f"""SELECT '{ym}' file, personnel_action_effective_date_yyyymm eff, separation_category_code cat,
                drp_indicator drp, appointment_type_code appt, age_bracket age, {LOS_Y} los_y, sum(count::INT) n
                FROM '{BASE}/{p}' GROUP BY ALL"""
        if ym >= ROOKIE_FROM:   # early departures for the rookie screen: under 2 years of service, tenure in months
            yield f"rookiesep2_{ym}_v{v}", f"""SELECT '{ym}' file, personnel_action_effective_date_yyyymm eff, agency_code,
                agency_subelement_code, any_value(agency_subelement) sub, occupational_series_code, appointment_type_code appt,
                separation_category_code cat, drp_indicator drp,
                CAST(round({SVC} * 12) AS INT) tenure_m, sum(count::INT) n
                FROM '{BASE}/{p}' WHERE {SVC} < 2 GROUP BY ALL"""
        if ym >= ICE_FROM:
            cat = "separation_category, separation_category_code, drp_indicator, appointment_type,"
            yield f"icesep2_{ym}_v{v}", f"SELECT {ICE_COLS.format(cat=cat, ym=ym, svc=SVC)} FROM '{BASE}/{p}' WHERE agency_subelement_code IN ('HSBB', 'HSBD')"
    for ym, (v, p) in FILES["accessions"].items():
        if ym >= START:
            yield f"acc_{ym}_v{v}", f"""SELECT '{ym}' file, personnel_action_effective_date_yyyymm eff, accession_category_code cat,
                agency_code, occupational_series_code, appointment_type_code appt, sum(count::INT) n FROM '{BASE}/{p}' GROUP BY ALL"""
            # fresh: under NEW_HIRE_LOS years of service at hire, i.e. no prior federal service; vet: veteran (service credit
            # can include military time, so prior service among veterans isn't necessarily civilian)
            yield f"ageacc2_{ym}_v{v}", f"""SELECT '{ym}' file, personnel_action_effective_date_yyyymm eff, accession_category_code cat,
                agency_code, occupational_series_code occ, appointment_type_code appt, age_bracket age, {LOS_Y} los_y,
                {SVC} < {NEW_HIRE_LOS} fresh, veteran_indicator vet, pathways_group pw,
                sum(count::INT) n FROM '{BASE}/{p}' GROUP BY ALL"""
            # new hires by education, for the education of hires and how much of its change is which occupations are hired for
            yield f"eduacc_{ym}_v{v}", f"""SELECT '{ym}' file, personnel_action_effective_date_yyyymm eff, agency_code, occupational_series_code occ,
                appointment_type_code appt, education_level_bracket edu, sum(count::INT) n FROM '{BASE}/{p}'
                WHERE accession_category_code IN ('AC', 'AD', 'AE') GROUP BY ALL"""
        if ym >= ROOKIE_FROM:   # new hires with no prior federal service (under 3 months of service at hire)
            yield f"rookieacc2_{ym}_v{v}", f"""SELECT '{ym}' file, personnel_action_effective_date_yyyymm eff, agency_code,
                agency_subelement_code, any_value(agency_subelement) sub, occupational_series_code, appointment_type_code appt,
                sum(count::INT) n FROM '{BASE}/{p}' WHERE accession_category_code IN ('AC', 'AD', 'AE')
                AND {SVC} < {NEW_HIRE_LOS} GROUP BY ALL"""
        if ym >= ICE_FROM:
            cat = "accession_category, accession_category_code, appointment_type,"
            yield f"iceacc2_{ym}_v{v}", f"SELECT {ICE_COLS.format(cat=cat, ym=ym, svc=SVC)} FROM '{BASE}/{p}' WHERE agency_subelement_code IN ('HSBB', 'HSBD')"
    for ym, (v, p) in FILES["employment"].items():
        if ym >= START and ym.endswith("01"):
            snap = f"DATE '{ym[:4]}-{ym[4:]}-15'"
            yield f"emp3_{ym}_v{v}", f"""SELECT '{ym}' snap, agency_code, agency_subelement_code, occupational_series_code, {los(svc(snap))} los,
                appointment_type_code appt, education_level_bracket edu, any_value(occupational_series) series,
                sum(count::INT) n FROM '{BASE}/{p}' GROUP BY ALL"""
            yield f"ageemp2_{ym}_v{v}", f"""SELECT '{ym}' snap, appointment_type_code appt, age_bracket age, {los_y(svc(snap))} los_y,
                sum(count::INT) n FROM '{BASE}/{p}' GROUP BY ALL"""
        elif ym >= MONTHLY_FROM:
            if ym == max(FILES["employment"]):   # agency names for the codes in the other tables
                yield f"agnames_{ym}_v{v}", f"""SELECT DISTINCT agency_code, agency FROM '{BASE}/{p}'"""
            yield f"hc_{ym}_v{v}", f"""SELECT '{ym}' snap, agency_code, occupational_series_code, appointment_type_code appt,
                sum(count::INT) n FROM '{BASE}/{p}' GROUP BY ALL"""


    # OPM's own length_of_service_years against the leave service date, by veteran status: the check that shows when OPM
    # changed how it reports years of service. Monthly files from MONTHLY_FROM on, and every January.
    for ds in ("separations", "accessions", "employment"):
        for ym, (v, p) in FILES[ds].items():
            if ym >= START and (ym.endswith("01") or ym >= MONTHLY_FROM):
                y = svc(f"DATE '{ym[:4]}-{ym[4:]}-15'") if ds == "employment" else SVC
                yield f"scdchk_{ds[:3]}_{ym}_v{v}", f"""SELECT '{ds}' ds, '{ym}' file, veteran_indicator vet, sum(count::INT) n,
                    sum(count::INT) FILTER (WHERE abs(try_cast(length_of_service_years AS DOUBLE) - {y}) < {SCD_TOL}) same,
                    sum(count::INT * try_cast(length_of_service_years AS DOUBLE)) FILTER (WHERE {y} < {MAX_LOS}) / sum(count::INT) FILTER (WHERE {y} < {MAX_LOS}) opm_mean,
                    sum(count::INT * {y}) FILTER (WHERE {y} < {MAX_LOS}) / sum(count::INT) FILTER (WHERE {y} < {MAX_LOS}) scd_mean
                    FROM '{BASE}/{p}' WHERE appointment_type_code IN {PERM} GROUP BY ALL"""

    # Years of service both ways, OPM's length_of_service_years as published and from the leave service date, on the same
    # records: the files build.py's same-months comparisons use (January to LAST_M of every year), and every January's staff.
    # Shows what reading OPM's field as published would do to the 20+ years quit rate and to prior service among new hires.
    opm = "try_cast(length_of_service_years AS DOUBLE)"
    band = lambda y: (f"CASE WHEN {y} IS NULL OR {y} >= {MAX_LOS} THEN NULL WHEN {y} < {BAND_CUTS[0]} THEN 'a' "
                      f"WHEN {y} < {BAND_CUTS[1]} THEN 'b' ELSE 'c' END")   # build.py's three bands (BANDS)
    last_m = LATEST[4:]
    for ds in ("separations", "accessions", "employment"):
        for ym, (v, p) in FILES[ds].items():
            if ym < START or (ym[4:] > last_m if ds != "employment" else not ym.endswith("01")):
                continue
            if ds == "separations":
                yield f"asissep_{ym}_v{v}", f"""SELECT '{ym}' file, personnel_action_effective_date_yyyymm eff, separation_category_code cat, drp_indicator drp,
                    veteran_indicator vet, {band(opm)} band_opm, {band(SVC)} band_scd, sum(count::INT) n
                    FROM '{BASE}/{p}' WHERE appointment_type_code IN {PERM} GROUP BY ALL"""
            elif ds == "accessions":
                yield f"asisacc_{ym}_v{v}", f"""SELECT '{ym}' file, personnel_action_effective_date_yyyymm eff, veteran_indicator vet,
                    {opm} >= {NEW_HIRE_LOS} prior_opm, {SVC} >= {NEW_HIRE_LOS} prior_scd, sum(count::INT) n FROM '{BASE}/{p}'
                    WHERE appointment_type_code IN {PERM} AND accession_category_code IN ('AC', 'AD', 'AE') GROUP BY ALL"""
            else:
                snap = svc(f"DATE '{ym[:4]}-{ym[4:]}-15'")
                yield f"asisemp_{ym}_v{v}", f"""SELECT '{ym}' snap, veteran_indicator vet, {band(opm)} band_opm, {band(snap)} band_scd, sum(count::INT) n
                    FROM '{BASE}/{p}' WHERE appointment_type_code IN {PERM} GROUP BY ALL"""

    for ds in ("accessions", "separations"):   # ICE and CBP records in every version OPM has published, for the republishing check
        for ym, vs in ALL[ds].items():
            for v, p in vs.items():
                if ym >= ICE_FROM:
                    yield f"ver_{ds[:3]}_{ym}_v{v}", f"""SELECT '{ds}' ds, '{ym}' file, {v} v, agency_subelement_code agy_code,
                        sum(count::INT) n FROM '{BASE}/{p}' WHERE agency_subelement_code IN ('HSBB', 'HSBD') GROUP BY ALL"""


PLAN = list(plan())
con = duckdb.connect()
con.execute("SET threads=3")   # few parallel requests, or HuggingFace rate-limits
ONLY = tuple(sys.argv[1:])   # python3 extract.py scdchk_ : read only the cache files with these prefixes, then stop
todo = [(name, sql) for name, sql in PLAN if not (CACHE / f"{name}.parquet").exists() and name.startswith(ONLY or "")]
print(len(todo), "files to read", flush=True)
for i, (name, sql) in enumerate(todo, 1):
    for attempt in range(1, 7):
        try:
            con.execute(f"COPY ({sql() if callable(sql) else sql}) TO '{CACHE}/{name}.tmp.parquet' (FORMAT parquet)")
            Path(f"{CACHE}/{name}.tmp.parquet").rename(CACHE / f"{name}.parquet")
            break
        except Exception as e:
            if attempt == 6:
                raise
            print(f"  {name}: {str(e)[:80]} - retry {attempt}", flush=True)
            time.sleep(20 * attempt)
    print(f"{i}/{len(todo)} {name}", flush=True)
    time.sleep(1)

if ONLY:
    sys.exit()
# Combine only the caches this run planned, so a superseded version left in data/cache/ is never counted.
for out, prefix in (("sep", "sep4_"), ("emp", "emp3_"), ("hc", "hc_"), ("acc", "acc_"), ("rookie_sep", "rookiesep2_"), ("rookie_acc", "rookieacc2_"),
                    ("acc_ice_cbp", "iceacc2_"), ("sep_ice_cbp", "icesep2_"), ("versions", "ver_"),
                    ("age_sep", "agesep2_"), ("age_acc", "ageacc2_"), ("age_emp", "ageemp2_"), ("agency_names", "agnames_"), ("scd_check", "scdchk_"), ("edu_acc", "eduacc_"),
                    ("asis_sep", "asissep_"), ("asis_acc", "asisacc_"), ("asis_emp", "asisemp_")):
    paths = [f"{CACHE}/{name}.parquet" for name, _ in PLAN if name.startswith(prefix)]
    assert paths, out
    con.execute(f"COPY (SELECT * FROM read_parquet({paths}, union_by_name=true) ORDER BY ALL) "
                f"TO '{DATA}/{out}.parquet' (FORMAT parquet, COMPRESSION zstd)")
    total = "" if out in ("agency_names", "scd_check") else f", sum({'count' if 'ice' in out else 'n'})"
    print(out, con.sql(f"SELECT count(*){total} FROM '{DATA}/{out}.parquet'").fetchone())

# ---- Outside sources, saved to data/sources/ and read by build.py ---------------------------------------------
SRC = DATA / "sources"
SRC.mkdir(exist_ok=True)
for name, url in SOURCES.items():
    if not (SRC / name).exists():
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "federal-attrition-patterns"})) as r:
            (SRC / name).write_bytes(r.read())
    print(name, (SRC / name).stat().st_size, "bytes")
# USAJOBS postings (the usajobs_historical archive): what ICE calls its law-enforcement (GL) jobs in series 1801 and 1811.
if not (SRC / "usajobs_ice_1801_1811.parquet").exists():
    con.execute(f"""COPY (SELECT usajobsControlNumber, positionOpenDate, payScale, positionTitle,
            json_extract_string(JobCategories, '$[0].series') series
        FROM read_parquet({[f"{USAJOBS}/historical_jobs_{y}.parquet" for y in range(int(USAJOBS_FROM[:4]), int(LATEST[:4]) + 1)]}, union_by_name=true)
        WHERE hiringAgencyCode = 'HSBB' AND positionOpenDate >= '{USAJOBS_FROM}' AND replace(left(positionOpenDate, 7), '-', '') <= '{LATEST}' AND (JobCategories LIKE '%1801%' OR JobCategories LIKE '%1811%')
        ORDER BY ALL) TO '{SRC}/usajobs_ice_1801_1811.parquet' (FORMAT parquet)""")
print("usajobs", con.sql(f"SELECT count(*) FROM '{SRC}/usajobs_ice_1801_1811.parquet'").fetchone())
