#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zenodo_inventory.py — Inventário fail-closed da comunidade Zenodo MatVerse.

Objetivo:
- Ler registros publicados da comunidade Zenodo `matverse`.
- Gerar inventário JSONL/JSON/CSV para o EVENTO-003.
- Não cria, não edita, não publica depósitos.
- Não imprime token.

Token:
- Canônico: ZENODO_ACCESS_TOKEN
- Alias aceito com warning: ZENODO_ACCEES_TOKEN  # typo preservado por compatibilidade operacional

Uso:
  python3 tools/zenodo_inventory.py --community matverse --limit 57 --out-dir artifacts/zenodo

Modo público sem token:
  python3 tools/zenodo_inventory.py --community matverse --limit 57 --no-token --out-dir artifacts/zenodo

Observação:
- Para registros públicos, Zenodo Records API pode responder sem token.
- Para dashboard/depósitos privados/drafts, use token real via env.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ZENODO_RECORDS_API = "https://zenodo.org/api/records"
CANONICAL_TOKEN_ENV = "ZENODO_ACCESS_TOKEN"
LEGACY_TYPO_TOKEN_ENV = "ZENODO_ACCEES_TOKEN"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def token_from_env(no_token: bool = False) -> Tuple[Optional[str], List[str]]:
    warnings: List[str] = []
    if no_token:
        return None, ["NO_TOKEN_MODE: using public Zenodo records endpoint only"]

    token = os.environ.get(CANONICAL_TOKEN_ENV)
    if token:
        return token, warnings

    typo_token = os.environ.get(LEGACY_TYPO_TOKEN_ENV)
    if typo_token:
        warnings.append(
            f"TOKEN_ENV_ALIAS_USED: {LEGACY_TYPO_TOKEN_ENV} detected; prefer {CANONICAL_TOKEN_ENV}"
        )
        return typo_token, warnings

    warnings.append(
        f"NO_TOKEN_FOUND: set {CANONICAL_TOKEN_ENV}; alias {LEGACY_TYPO_TOKEN_ENV} is accepted with warning"
    )
    return None, warnings


def http_get_json(url: str, token: Optional[str], timeout: int = 30) -> Dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "matverse-zenodo-inventory/0.1",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} from Zenodo: {msg[:500]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error contacting Zenodo: {e}") from e


def build_records_url(community: str, page: int, size: int, sort: str) -> str:
    # InvenioRDM/Zenodo record search supports q, page, size, sort and communities filter.
    # The public UI path /communities/{id}/records maps to the same indexed record corpus.
    query = {
        "q": f"communities:{community}",
        "page": str(page),
        "size": str(size),
        "sort": sort,
    }
    return f"{ZENODO_RECORDS_API}?{urllib.parse.urlencode(query)}"


def extract_hits(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    hits = payload.get("hits", {})
    if isinstance(hits, dict):
        values = hits.get("hits", [])
        if isinstance(values, list):
            return values
    # Backward-compatible fallback for older list-like responses.
    if isinstance(payload, list):
        return payload
    return []


def total_hits(payload: Dict[str, Any]) -> Optional[int]:
    hits = payload.get("hits", {})
    total = hits.get("total") if isinstance(hits, dict) else None
    if isinstance(total, dict):
        value = total.get("value")
        return int(value) if value is not None else None
    if isinstance(total, int):
        return total
    return None


def first_creator(metadata: Dict[str, Any]) -> Dict[str, Any]:
    creators = metadata.get("creators") or metadata.get("creators", [])
    if isinstance(creators, list) and creators:
        c = creators[0]
        if isinstance(c, dict):
            return c
    return {}


def creator_name(c: Dict[str, Any]) -> str:
    # InvenioRDM may use person_or_org/name; legacy may use name directly.
    if "name" in c and isinstance(c["name"], str):
        return c["name"]
    po = c.get("person_or_org")
    if isinstance(po, dict):
        return str(po.get("name") or "")
    return ""


def creator_orcid(c: Dict[str, Any]) -> str:
    if "orcid" in c and isinstance(c["orcid"], str):
        return c["orcid"]
    po = c.get("person_or_org")
    if isinstance(po, dict):
        identifiers = po.get("identifiers") or []
        if isinstance(identifiers, list):
            for ident in identifiers:
                if isinstance(ident, dict) and str(ident.get("scheme", "")).lower() == "orcid":
                    return str(ident.get("identifier") or "")
    return ""


def normalize_resource_type(metadata: Dict[str, Any]) -> str:
    rt = metadata.get("resource_type") or metadata.get("upload_type") or ""
    if isinstance(rt, dict):
        return str(rt.get("id") or rt.get("title", {}).get("en") or rt.get("title") or "")
    return str(rt)


def normalize_record(hit: Dict[str, Any], index: int, community: str) -> Dict[str, Any]:
    metadata = hit.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    creator = first_creator(metadata)

    title = str(metadata.get("title") or hit.get("title") or "").strip()
    description = str(metadata.get("description") or metadata.get("abstract") or "").strip()
    doi = str(metadata.get("doi") or hit.get("doi") or "").strip()
    recid = str(hit.get("id") or hit.get("recid") or hit.get("record_id") or "")
    links = hit.get("links") if isinstance(hit.get("links"), dict) else {}

    files = []
    files_obj = hit.get("files")
    if isinstance(files_obj, list):
        for f in files_obj:
            if isinstance(f, dict):
                files.append({
                    "key": f.get("key") or f.get("filename") or "",
                    "size": f.get("size"),
                    "checksum": f.get("checksum") or "",
                })
    elif isinstance(files_obj, dict):
        for entry in files_obj.get("entries", []) if isinstance(files_obj.get("entries"), list) else []:
            if isinstance(entry, dict):
                files.append({
                    "key": entry.get("key") or "",
                    "size": entry.get("size"),
                    "checksum": entry.get("checksum") or "",
                })

    keywords = metadata.get("keywords") or metadata.get("subjects") or []
    if not isinstance(keywords, list):
        keywords = []

    record = {
        "record_index": index,
        "zenodo_record_id_or_doi": doi or recid,
        "record_id": recid,
        "doi": doi,
        "title": title,
        "resource_type": normalize_resource_type(metadata),
        "publication_date": str(metadata.get("publication_date") or metadata.get("imprint", {}).get("date") if isinstance(metadata.get("imprint"), dict) else ""),
        "version": str(metadata.get("version") or ""),
        "authors": [creator_name(creator)] if creator else [],
        "orcid": creator_orcid(creator),
        "affiliation": str(creator.get("affiliation") or ""),
        "abstract_or_description": description,
        "keywords": keywords,
        "license": metadata.get("license") or metadata.get("rights") or "",
        "access_right": str(metadata.get("access_right") or metadata.get("access") or "open"),
        "community_identifier": community,
        "file_paths_or_existing_files": files,
        "related_identifiers": metadata.get("related_identifiers") or metadata.get("related_identifiers", []),
        "source_status": "ZENODO_PUBLIC_RECORD",
        "doi_status": "PASS" if doi else "HOLD_DOI_OR_RECORD_ONLY",
        "duplicate_group": "",
        "claim_hygiene_status": "PASS_METADATA_INVENTORY_ONLY",
        "manifest_sha256": "",
        "links": {
            "self": links.get("self", ""),
            "html": links.get("html") or links.get("self_html") or links.get("latest_html") or "",
            "doi": f"https://doi.org/{doi}" if doi else "",
        },
        "notes": "",
    }
    stable = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    record["manifest_sha256"] = sha256_text(stable)
    return record


def fetch_community_records(community: str, limit: int, page_size: int, sort: str, token: Optional[str], sleep_s: float) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    page = 1
    observed_total: Optional[int] = None
    while len(records) < limit:
        url = build_records_url(community, page, page_size, sort)
        payload = http_get_json(url, token=token)
        if observed_total is None:
            observed_total = total_hits(payload)
        hits = extract_hits(payload)
        if not hits:
            break
        for hit in hits:
            if len(records) >= limit:
                break
            records.append(normalize_record(hit, len(records) + 1, community))
        page += 1
        if sleep_s > 0:
            time.sleep(sleep_s)

    meta = {
        "community_identifier": community,
        "requested_limit": limit,
        "records_collected": len(records),
        "observed_total": observed_total,
        "sort": sort,
        "generated_at": utc_now_iso(),
        "api": ZENODO_RECORDS_API,
    }
    return records, meta


def detect_duplicates(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_title: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        key = " ".join(r.get("title", "").lower().split())
        if key:
            by_title.setdefault(key, []).append(r)
    rows = []
    group_id = 1
    for title_key, group in sorted(by_title.items()):
        if len(group) > 1:
            gid = f"DUP-{group_id:03d}"
            for r in group:
                r["duplicate_group"] = gid
            rows.append({
                "duplicate_group": gid,
                "title_normalized": title_key,
                "count": len(group),
                "records": [
                    {
                        "record_index": g["record_index"],
                        "record_id": g["record_id"],
                        "doi": g["doi"],
                        "title": g["title"],
                        "publication_date": g["publication_date"],
                        "version": g["version"],
                    }
                    for g in group
                ],
            })
            group_id += 1
    return rows


def write_outputs(records: List[Dict[str, Any]], meta: Dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    duplicates = detect_duplicates(records)

    inventory = {
        "schema": "matverse.zenodo_existing_records_inventory.v0.1",
        "status": "PASS_INVENTORY" if records else "FAIL_EMPTY_INVENTORY",
        "meta": meta,
        "records": records,
    }
    (out_dir / "zenodo_existing_records_inventory.json").write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (out_dir / "zenodo_doi_ledger.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps({
                "record_index": r["record_index"],
                "record_id": r["record_id"],
                "doi": r["doi"],
                "title": r["title"],
                "resource_type": r["resource_type"],
                "community_identifier": r["community_identifier"],
                "doi_status": r["doi_status"],
                "manifest_sha256": r["manifest_sha256"],
            }, ensure_ascii=False, sort_keys=True) + "\n")

    csv_fields = [
        "record_index", "zenodo_record_id_or_doi", "record_id", "doi", "title", "resource_type",
        "publication_date", "version", "authors", "orcid", "affiliation", "access_right",
        "community_identifier", "doi_status", "duplicate_group", "claim_hygiene_status",
        "manifest_sha256", "notes",
    ]
    with (out_dir / "zenodo_batch_57.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields)
        w.writeheader()
        for r in records:
            row = {k: r.get(k, "") for k in csv_fields}
            row["authors"] = "; ".join(r.get("authors") or [])
            w.writerow(row)

    dup_md = ["# Zenodo duplicate review", "", f"Generated: {meta['generated_at']}", ""]
    if not duplicates:
        dup_md.append("No exact title duplicates detected.")
    else:
        for d in duplicates:
            dup_md.append(f"## {d['duplicate_group']} — {d['count']} records")
            dup_md.append("")
            dup_md.append(f"Normalized title: `{d['title_normalized']}`")
            dup_md.append("")
            dup_md.append("| index | record_id | doi | date | version | title |")
            dup_md.append("|---:|---|---|---|---|---|")
            for r in d["records"]:
                dup_md.append(
                    f"| {r['record_index']} | {r['record_id']} | {r['doi']} | {r['publication_date']} | {r['version']} | {r['title']} |"
                )
            dup_md.append("")
    (out_dir / "zenodo_duplicate_review.md").write_text("\n".join(dup_md) + "\n", encoding="utf-8")

    report = {
        "schema": "matverse.zenodo_submission_report.v0.1",
        "status": "PASS_INVENTORY_READY" if len(records) == meta.get("requested_limit") else "HOLD_COUNT_MISMATCH",
        "records_collected": len(records),
        "requested_limit": meta.get("requested_limit"),
        "observed_total": meta.get("observed_total"),
        "duplicates_detected": len(duplicates),
        "outputs": [
            "zenodo_existing_records_inventory.json",
            "zenodo_batch_57.csv",
            "zenodo_doi_ledger.jsonl",
            "zenodo_duplicate_review.md",
        ],
        "generated_at": meta["generated_at"],
    }
    (out_dir / "zenodo_submission_report.md").write_text(
        "# Zenodo submission report\n\n```json\n" + json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n```\n",
        encoding="utf-8",
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build MatVerse Zenodo community inventory")
    ap.add_argument("--community", default="matverse")
    ap.add_argument("--limit", type=int, default=57)
    ap.add_argument("--page-size", type=int, default=25)
    ap.add_argument("--sort", default="newest")
    ap.add_argument("--out-dir", default="artifacts/zenodo")
    ap.add_argument("--no-token", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args(list(argv) if argv is not None else None)

    token, warnings = token_from_env(no_token=args.no_token)
    for w in warnings:
        print(f"WARN {w}", file=sys.stderr)

    try:
        records, meta = fetch_community_records(
            community=args.community,
            limit=args.limit,
            page_size=args.page_size,
            sort=args.sort,
            token=token,
            sleep_s=args.sleep,
        )
        meta["warnings"] = warnings
        write_outputs(records, meta, Path(args.out_dir))
    except Exception as e:
        print(f"FAIL zenodo inventory: {e}", file=sys.stderr)
        return 1

    print(f"PASS inventory: {len(records)} records → {args.out_dir}")
    if len(records) != args.limit:
        print(f"WARN expected {args.limit}, collected {len(records)}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
