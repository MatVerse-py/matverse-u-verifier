#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zenodo_batch_submit.py — Submissão fail-closed dos 57 registros MatVerse à comunidade Zenodo.

Escopo:
- Lê um CSV/manifest de 57 registros.
- Monta metadata Zenodo com communities=[{"identifier": "matverse"}].
- Cria drafts, envia arquivos, reserva DOI e opcionalmente publica.
- Por padrão NÃO faz chamadas de escrita e NÃO publica nada.

Uso seguro — dry-run sem rede:
  python3 tools/zenodo_batch_submit.py \
    --csv artifacts/zenodo/zenodo_batch_57.csv \
    --community matverse \
    --out-dir artifacts/zenodo_submission

Sandbox — cria drafts, mas não publica:
  export SANDBOX_ZENODO_ACCESS_TOKEN="..."
  python3 tools/zenodo_batch_submit.py \
    --csv artifacts/zenodo/zenodo_batch_57.csv \
    --sandbox --create-drafts \
    --out-dir artifacts/zenodo_submission_sandbox

Produção — cria drafts, mas não publica:
  export ZENODO_ACCESS_TOKEN="..."
  python3 tools/zenodo_batch_submit.py \
    --csv artifacts/zenodo/zenodo_batch_57.csv \
    --production --create-drafts \
    --out-dir artifacts/zenodo_submission_prod

Publicação explícita — perigoso, irreversível:
  python3 tools/zenodo_batch_submit.py \
    --csv artifacts/zenodo/zenodo_batch_57.csv \
    --production --create-drafts --publish --i-understand-this-publishes \
    --out-dir artifacts/zenodo_submission_prod

Variáveis de ambiente:
- Produção canônica: ZENODO_ACCESS_TOKEN
- Produção alias legado: ZENODO_ACCEES_TOKEN  # typo aceito com warning
- Sandbox canônica: SANDBOX_ZENODO_ACCESS_TOKEN
- Sandbox aliases: SANDBOX_ZENODO_TOKEN, SANDBOX_ZENODO_ACCEES_TOKEN

Token nunca é impresso. Use scopes Zenodo: deposit:write e deposit:actions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

PROD_API = "https://zenodo.org/api"
SANDBOX_API = "https://sandbox.zenodo.org/api"
COMMUNITY_DEFAULT = "matverse"
EXPECTED_COUNT_DEFAULT = 57

TOKEN_ENV = "ZENODO_ACCESS_TOKEN"
TOKEN_ENV_TYPO = "ZENODO_ACCEES_TOKEN"
SANDBOX_TOKEN_ENV = "SANDBOX_ZENODO_ACCESS_TOKEN"
SANDBOX_TOKEN_ALIAS = "SANDBOX_ZENODO_TOKEN"
SANDBOX_TOKEN_TYPO = "SANDBOX_ZENODO_ACCEES_TOKEN"

# Zenodo controlled values used by the legacy deposit API.
PUBLICATION_SUBTYPE_MAP = {
    "journal article": "article",
    "journal_article": "article",
    "article": "article",
    "preprint": "preprint",
    "working paper": "workingpaper",
    "working_paper": "workingpaper",
    "report": "report",
    "technical report": "report",
    "technicalnote": "technicalnote",
    "technical note": "technicalnote",
    "publication": "technicalnote",
    "publication_other": "other",
}

UPLOAD_TYPE_MAP = {
    "dataset": "dataset",
    "software": "software",
    "publication": "publication",
    "journal article": "publication",
    "journal_article": "publication",
    "preprint": "publication",
    "working paper": "publication",
    "working_paper": "publication",
    "report": "publication",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(filename: str) -> str:
    name = Path(filename).name.strip()
    if not name or name in {".", ".."}:
        raise ValueError(f"invalid filename: {filename!r}")
    # Avoid path traversal/control chars in remote object names.
    if "/" in name or "\\" in name or any(ord(c) < 32 for c in name):
        raise ValueError(f"unsafe filename: {filename!r}")
    return name


def normalize_key(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def split_list(value: str) -> List[str]:
    if not value:
        return []
    # Accept JSON array, semicolon or comma separated.
    value = str(value).strip()
    if not value:
        return []
    if value.startswith("["):
        try:
            arr = json.loads(value)
            if isinstance(arr, list):
                out = []
                for item in arr:
                    if isinstance(item, str):
                        out.append(item)
                    elif isinstance(item, dict):
                        key = item.get("key") or item.get("path") or item.get("filename")
                        if key:
                            out.append(str(key))
                return [x.strip() for x in out if x.strip()]
        except json.JSONDecodeError:
            pass
    sep = ";" if ";" in value else ","
    return [x.strip() for x in value.split(sep) if x.strip()]


def token_from_env(sandbox: bool) -> Tuple[Optional[str], List[str]]:
    warnings: List[str] = []
    if sandbox:
        for env in (SANDBOX_TOKEN_ENV, SANDBOX_TOKEN_ALIAS, SANDBOX_TOKEN_TYPO):
            val = os.environ.get(env)
            if val:
                if env != SANDBOX_TOKEN_ENV:
                    warnings.append(f"TOKEN_ENV_ALIAS_USED: {env}; prefer {SANDBOX_TOKEN_ENV}")
                return val, warnings
        warnings.append(f"NO_SANDBOX_TOKEN_FOUND: set {SANDBOX_TOKEN_ENV}")
        return None, warnings

    token = os.environ.get(TOKEN_ENV)
    if token:
        return token, warnings
    typo = os.environ.get(TOKEN_ENV_TYPO)
    if typo:
        warnings.append(f"TOKEN_ENV_ALIAS_USED: {TOKEN_ENV_TYPO}; prefer {TOKEN_ENV}")
        return typo, warnings
    warnings.append(f"NO_PROD_TOKEN_FOUND: set {TOKEN_ENV}; alias {TOKEN_ENV_TYPO} accepted with warning")
    return None, warnings


def request_json(
    method: str,
    url: str,
    token: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "matverse-zenodo-batch-submit/0.1",
    }
    body: Optional[bytes] = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {method} {url}: {err[:1000]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"NETWORK {method} {url}: {e}") from e


def upload_file(bucket_url: str, path: Path, token: str, timeout: int = 300) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(str(path))
    filename = safe_name(path.name)
    url = bucket_url.rstrip("/") + "/" + urllib.parse.quote(filename)
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "matverse-zenodo-batch-submit/0.1",
    }
    with path.open("rb") as fp:
        req = urllib.request.Request(url, data=fp, headers=headers, method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code} PUT file {filename}: {err[:1000]}") from e


def load_rows(csv_path: Path) -> List[Dict[str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]


def find_local_files(row: Dict[str, str], files_root: Path) -> List[Path]:
    candidates: List[str] = []
    for col in ("local_files", "file_paths", "paper_pdf_path", "pdf_path", "paper_md_path", "md_path"):
        candidates.extend(split_list(row.get(col, "")))
    # If inventory CSV contains existing remote file names, do NOT treat them as local unless they exist.
    out: List[Path] = []
    seen = set()
    for c in candidates:
        p = Path(c)
        if not p.is_absolute():
            p = files_root / p
        p = p.resolve()
        if str(p) in seen:
            continue
        seen.add(str(p))
        if p.exists() and p.is_file():
            out.append(p)
    return out


def validate_row(row: Dict[str, str], index: int, files: List[Path], require_files: bool) -> Tuple[bool, List[str]]:
    issues = []
    if not (row.get("title") or "").strip():
        issues.append("BLOCK_METADATA:title_missing")
    desc = (row.get("abstract_or_description") or row.get("description") or row.get("abstract") or "").strip()
    if not desc:
        issues.append("BLOCK_METADATA:description_missing")
    authors = row.get("authors") or row.get("author") or ""
    if not authors.strip():
        issues.append("BLOCK_AUTHORSHIP:authors_missing")
    orcid = (row.get("orcid") or "").strip()
    if orcid and not re.match(r"^\d{4}-\d{4}-\d{4}-\d{3}[0-9X]$", orcid):
        issues.append("BLOCK_AUTHORSHIP:orcid_malformed")
    if require_files and not files:
        issues.append("BLOCK_UPLOAD:no_local_files")
    return len([i for i in issues if i.startswith("BLOCK")]) == 0, issues


def build_creators(row: Dict[str, str]) -> List[Dict[str, str]]:
    raw = row.get("authors") or row.get("author") or ""
    names = [x.strip() for x in re.split(r";", raw) if x.strip()] or [raw.strip()]
    out = []
    for i, name in enumerate([n for n in names if n]):
        c = {"name": name}
        if i == 0:
            if row.get("affiliation"):
                c["affiliation"] = row["affiliation"].strip()
            if row.get("orcid"):
                c["orcid"] = row["orcid"].strip()
        out.append(c)
    return out


def build_metadata(row: Dict[str, str], community: str, prereserve_doi: bool) -> Dict[str, Any]:
    resource = normalize_key(row.get("resource_type") or row.get("upload_type") or "publication")
    upload_type = UPLOAD_TYPE_MAP.get(resource, "publication")

    metadata: Dict[str, Any] = {
        "title": (row.get("title") or "").strip(),
        "upload_type": upload_type,
        "description": (row.get("abstract_or_description") or row.get("description") or row.get("abstract") or "").strip(),
        "creators": build_creators(row),
        "access_right": (row.get("access_right") or "open").strip() or "open",
        "communities": [{"identifier": community}],
        "keywords": split_list(row.get("keywords", "")) or ["MatVerse", "verifiable systems"],
        "notes": (row.get("notes") or "").strip(),
    }

    if upload_type == "publication":
        metadata["publication_type"] = PUBLICATION_SUBTYPE_MAP.get(resource, "technicalnote")

    # For open access, Zenodo requires a license. Keep existing when available.
    license_value = (row.get("license") or "cc-by-4.0").strip()
    if license_value:
        metadata["license"] = license_value

    pub_date = (row.get("publication_date") or "").strip()
    if pub_date:
        metadata["publication_date"] = pub_date

    version = (row.get("version") or "").strip()
    if version:
        metadata["version"] = version

    related = row.get("related_identifiers") or ""
    if related.strip():
        try:
            parsed = json.loads(related)
            if isinstance(parsed, list):
                metadata["related_identifiers"] = parsed
        except json.JSONDecodeError:
            pass

    # Reserve DOI for drafts so DOI can be inserted into PDFs before publication.
    if prereserve_doi:
        metadata["prereserve_doi"] = True

    return {"metadata": metadata}


def create_deposition(api_base: str, token: str) -> Dict[str, Any]:
    return request_json("POST", api_base.rstrip("/") + "/deposit/depositions", token, payload={})


def update_metadata(deposition: Dict[str, Any], metadata_payload: Dict[str, Any], token: str) -> Dict[str, Any]:
    url = deposition.get("links", {}).get("self")
    if not url:
        raise RuntimeError("deposition lacks links.self")
    return request_json("PUT", url, token, payload=metadata_payload)


def publish_deposition(deposition: Dict[str, Any], token: str) -> Dict[str, Any]:
    url = deposition.get("links", {}).get("publish")
    if not url:
        dep_id = deposition.get("id")
        if not dep_id:
            raise RuntimeError("deposition lacks publish link and id")
        # fallback, normally not needed
        url = f"{PROD_API}/deposit/depositions/{dep_id}/actions/publish"
    return request_json("POST", url, token, payload=None)


def process_row(
    row: Dict[str, str],
    index: int,
    api_base: str,
    token: Optional[str],
    community: str,
    files_root: Path,
    create_drafts: bool,
    publish: bool,
    prereserve_doi: bool,
    require_files: bool,
    sleep_s: float,
) -> Dict[str, Any]:
    files = find_local_files(row, files_root)
    ok, issues = validate_row(row, index, files, require_files=require_files)
    record = {
        "record_index": index,
        "title": row.get("title", ""),
        "existing_record_id_or_doi": row.get("zenodo_record_id_or_doi") or row.get("record_id") or row.get("doi") or "",
        "community_identifier": community,
        "local_files": [str(p) for p in files],
        "local_file_sha256": {p.name: sha256_file(p) for p in files},
        "validation_issues": issues,
        "action": "DRY_RUN",
        "status": "HOLD_VALIDATION" if not ok else "READY",
        "deposition_id": None,
        "reserved_doi": None,
        "published_doi": None,
        "links": {},
    }

    metadata_payload = build_metadata(row, community=community, prereserve_doi=prereserve_doi)
    record["metadata_preview_sha256"] = hashlib.sha256(
        json.dumps(metadata_payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    if not ok:
        record["action"] = "BLOCKED_BEFORE_API"
        return record
    if not create_drafts:
        record["action"] = "DRY_RUN_READY_TO_CREATE_DRAFT"
        return record
    if token is None:
        record["action"] = "BLOCKED_NO_TOKEN"
        record["status"] = "FAIL_NO_TOKEN"
        return record

    dep = create_deposition(api_base, token)
    record["deposition_id"] = dep.get("id")
    record["links"] = dep.get("links", {})
    bucket = dep.get("links", {}).get("bucket")
    if not bucket:
        raise RuntimeError(f"deposition {record['deposition_id']} lacks bucket link")

    uploaded = []
    for p in files:
        uploaded.append(upload_file(bucket, p, token))
        if sleep_s > 0:
            time.sleep(sleep_s)
    record["uploaded_files"] = uploaded

    dep2 = update_metadata(dep, metadata_payload, token)
    record["status"] = "DRAFT_CREATED"
    record["action"] = "CREATED_DRAFT"
    record["links"] = dep2.get("links", record["links"])
    prereserved = dep2.get("metadata", {}).get("prereserve_doi")
    if isinstance(prereserved, dict):
        record["reserved_doi"] = prereserved.get("doi")

    if publish:
        pub = publish_deposition(dep2, token)
        record["status"] = "PUBLISHED"
        record["action"] = "PUBLISHED"
        record["published_doi"] = pub.get("doi") or pub.get("metadata", {}).get("doi") or record.get("reserved_doi")
        record["links"] = pub.get("links", record["links"])

    return record


def write_report(results: List[Dict[str, Any]], out_dir: Path, meta: Dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "zenodo_batch_submit_results.json").write_text(
        json.dumps({"schema": "matverse.zenodo_batch_submit_results.v0.1", "meta": meta, "results": results}, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (out_dir / "zenodo_submission_doi_ledger.jsonl").open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({
                "record_index": r["record_index"],
                "title": r["title"],
                "status": r["status"],
                "action": r["action"],
                "deposition_id": r.get("deposition_id"),
                "reserved_doi": r.get("reserved_doi"),
                "published_doi": r.get("published_doi"),
                "metadata_preview_sha256": r.get("metadata_preview_sha256"),
            }, ensure_ascii=False, sort_keys=True) + "\n")

    counts: Dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    lines = [
        "# Zenodo batch submission report",
        "",
        f"Generated: {meta['generated_at']}",
        f"Mode: {meta['mode']}",
        f"Community: `{meta['community_identifier']}`",
        f"Rows: {meta['row_count']}",
        "",
        "## Status counts",
        "",
        "| status | count |",
        "|---|---:|",
    ]
    for k, v in sorted(counts.items()):
        lines.append(f"| `{k}` | {v} |")
    lines.extend(["", "## Blocked rows", "", "| index | status | title | issues |", "|---:|---|---|---|"])
    for r in results:
        if str(r["status"]).startswith("FAIL") or str(r["status"]).startswith("HOLD"):
            issues = "; ".join(r.get("validation_issues") or [])
            lines.append(f"| {r['record_index']} | `{r['status']}` | {r['title']} | {issues} |")
    (out_dir / "zenodo_batch_submit_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Submit 57 MatVerse papers/records to Zenodo community")
    ap.add_argument("--csv", default="artifacts/zenodo/zenodo_batch_57.csv")
    ap.add_argument("--community", default=COMMUNITY_DEFAULT)
    ap.add_argument("--files-root", default=".")
    ap.add_argument("--out-dir", default="artifacts/zenodo_submission")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--sandbox", action="store_true", help="Use sandbox.zenodo.org")
    mode.add_argument("--production", action="store_true", help="Use zenodo.org production")
    ap.add_argument("--create-drafts", action="store_true", help="Actually create Zenodo draft depositions")
    ap.add_argument("--publish", action="store_true", help="Publish created drafts (requires confirmation flag)")
    ap.add_argument("--i-understand-this-publishes", action="store_true", help="Required with --publish")
    ap.add_argument("--prereserve-doi", action="store_true", default=True)
    ap.add_argument("--no-prereserve-doi", dest="prereserve_doi", action="store_false")
    ap.add_argument("--require-files", action="store_true", default=True)
    ap.add_argument("--allow-metadata-only", dest="require_files", action="store_false")
    ap.add_argument("--expected-count", type=int, default=EXPECTED_COUNT_DEFAULT)
    ap.add_argument("--sleep", type=float, default=0.25)
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.publish and not args.i_understand_this_publishes:
        print("FAIL: --publish requires --i-understand-this-publishes", file=sys.stderr)
        return 2
    if args.publish and not args.create_drafts:
        print("FAIL: --publish requires --create-drafts", file=sys.stderr)
        return 2
    if args.create_drafts and not (args.sandbox or args.production):
        print("FAIL: --create-drafts requires --sandbox or --production", file=sys.stderr)
        return 2

    api_base = SANDBOX_API if args.sandbox else PROD_API
    mode_name = "SANDBOX" if args.sandbox else "PRODUCTION" if args.production else "DRY_RUN_NO_NETWORK"
    token, warnings = token_from_env(sandbox=args.sandbox) if args.create_drafts else (None, [])
    for w in warnings:
        print(f"WARN {w}", file=sys.stderr)

    rows = load_rows(Path(args.csv))
    if len(rows) != args.expected_count:
        print(f"WARN expected {args.expected_count} rows, CSV has {len(rows)}", file=sys.stderr)

    results = []
    for i, row in enumerate(rows, start=1):
        try:
            res = process_row(
                row=row,
                index=i,
                api_base=api_base,
                token=token,
                community=args.community,
                files_root=Path(args.files_root).resolve(),
                create_drafts=args.create_drafts,
                publish=args.publish,
                prereserve_doi=args.prereserve_doi,
                require_files=args.require_files,
                sleep_s=args.sleep,
            )
        except Exception as e:
            res = {
                "record_index": i,
                "title": row.get("title", ""),
                "status": "FAIL_EXCEPTION",
                "action": "EXCEPTION",
                "error": str(e),
                "community_identifier": args.community,
            }
        results.append(res)
        status = res.get("status")
        title = (res.get("title") or "")[:80]
        print(f"{i:03d}/{len(rows):03d} {status}: {title}")
        if args.sleep > 0:
            time.sleep(args.sleep)

    meta = {
        "schema": "matverse.zenodo_batch_submit.v0.1",
        "generated_at": utc_now(),
        "mode": mode_name,
        "api_base": api_base,
        "community_identifier": args.community,
        "row_count": len(rows),
        "expected_count": args.expected_count,
        "create_drafts": args.create_drafts,
        "publish": args.publish,
        "prereserve_doi": args.prereserve_doi,
        "warnings": warnings,
    }
    write_report(results, Path(args.out_dir), meta)

    fail_count = sum(1 for r in results if str(r.get("status", "")).startswith("FAIL"))
    hold_count = sum(1 for r in results if str(r.get("status", "")).startswith("HOLD"))
    print(f"DONE {mode_name}: {len(results)} rows, fail={fail_count}, hold={hold_count}, out={args.out_dir}")
    if fail_count:
        return 1
    if hold_count or len(rows) != args.expected_count:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
