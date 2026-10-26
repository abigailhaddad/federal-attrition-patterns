# Everything, in order: python3 run.py  (add --verify to also re-check every file against OPM's copy, which is slow)
# extract.py reads only files it doesn't already have; build.py writes the charts and charts/facts.md; spot_check.py
# recomputes the headline numbers from OPM's raw files.
import subprocess, sys

steps = ["extract.py"] + (["verify_opm.py"] if "--verify" in sys.argv else []) + ["build.py", "spot_check.py"]
for step in steps:
    print(f"== {step}", flush=True)
    subprocess.run([sys.executable, step], check=True)
