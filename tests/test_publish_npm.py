"""Garde : aucun workflow ne publie sur npm.

Décision du 2026-11-21 : la sortie TypeScript (`ts/`) ne se publie pas sur npm ; ses hôtes l'installent par épingle
GitHub sur le tag (`github:oto-now/connectors#<tag ou sha>&path:/ts`). Le paquet `@otomata_tech/connectors` n'a jamais
existé sur npm, et le job qui le publiait échouait à chaque version. Le job `npm` de `.github/workflows/publish.yml`
reste : il vérifie, sur le tag, que la sortie TS tient (version, typecheck, tests, `npm pack`), sans jeton ni archive
conservée. Le geste de publication : `docs/release.md`.
"""
from __future__ import annotations

import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((REPO / ".github/workflows").glob("*.yml"))
NPM_PUBLISH = re.compile(r"\bnpm\s+publish\b|registry\.npmjs\.org|NPM_TOKEN|NODE_AUTH_TOKEN")


def _steps(path: pathlib.Path):
    for name, job in (yaml.safe_load(path.read_text()).get("jobs") or {}).items():
        for step in job.get("steps") or []:
            yield name, step


def test_no_workflow_publishes_to_npm():
    hits = [
        f"{path.name}: {job}: {step.get('name') or step.get('run') or step.get('uses')}"
        for path in WORKFLOWS
        for job, step in _steps(path)
        if NPM_PUBLISH.search(yaml.safe_dump(step))
    ]
    assert not hits, f"no npm publication (decision 2026-11-21, docs/release.md): {hits}"


def test_ts_output_is_still_checked_on_the_tag():
    steps = yaml.safe_load((REPO / ".github/workflows/publish.yml").read_text())["jobs"]["npm"]["steps"]
    runs = [step.get("run", "") for step in steps]
    for command in ("npm ci", "npm run typecheck", "npm test", "npm pack"):
        assert command in runs, f"publish.yml job npm: `{command}` missing, got: {runs}"
