"""Build phase-library.html and jobs.html with embedded JSON data.

Pure rendering pipeline: reads Phase 3 outputs and the static HTML/JS
templates and substitutes the JSON payloads inline so the resulting
HTML pages work when opened directly via file:// (no fetch, no server).
"""
import json
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CFG = ROOT / "config"
OUT = ROOT / "monday-binder"


def load_json(p):
    with open(p) as f:
        return json.load(f)


def load_yaml(p):
    with open(p) as f:
        return yaml.safe_load(f)


def build():
    phase_instances = load_json(DATA / "phase-instances-v2.json")
    phase_medians = load_json(DATA / "phase-medians.json")
    sub_rollups = load_json(DATA / "sub-phase-rollups.json")
    job_stages = load_json(DATA / "job-stages.json")
    bursts = load_json(DATA / "bursts.json")
    taxonomy = load_yaml(CFG / "phase-taxonomy.yaml")

    bundle = {
        "today": job_stages.get("today"),
        "instances": phase_instances["instances"],
        "medians": phase_medians["medians"],
        "rollups": sub_rollups["rollups"],
        "jobs": job_stages["jobs"],
        "bursts": bursts["bursts"],
        "taxonomy": taxonomy["phases"],
        "taxonomy_meta": taxonomy.get("metadata", {}),
    }

    bundle_json = json.dumps(bundle, separators=(",", ":"))

    pl_template_path = OUT / "phase-library.template.html"
    jobs_template_path = OUT / "jobs.template.html"

    pl_template = pl_template_path.read_text(encoding="utf-8")
    jobs_template = jobs_template_path.read_text(encoding="utf-8")

    pl_out = pl_template.replace("__SI_DATA_BUNDLE__", bundle_json)
    jobs_out = jobs_template.replace("__SI_DATA_BUNDLE__", bundle_json)

    (OUT / "phase-library.html").write_text(pl_out, encoding="utf-8")
    (OUT / "jobs.html").write_text(jobs_out, encoding="utf-8")

    print(f"phase-library.html: {(OUT / 'phase-library.html').stat().st_size:,} bytes")
    print(f"jobs.html:          {(OUT / 'jobs.html').stat().st_size:,} bytes")
    print(f"data bundle:        {len(bundle_json):,} bytes")


if __name__ == "__main__":
    build()
