"""Check the frozen evidence snapshot at legacy-code/frozen-sources-20261105/.

Default run verifies every copied file against the SHA256 recorded in manifest.json.
With --evidence it additionally checks that each hard-pinned entry's hash still appears
in at least one of the evidence files the manifest points at (verification/ pin files or
the legacy freeze files carrying implicit pins).  Exit code 0 means everything passed.

Usage:
    python tools/verify_frozen_sources.py
    python tools/verify_frozen_sources.py --evidence
    python tools/verify_frozen_sources.py --manifest <path> --root <project root>
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = 'legacy-code/frozen-sources-20261105'
HEX64 = re.compile(r'(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])')


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def resolve_evidence(root, reference):
    """verification/ pin files are relative to verification/; implicit refs to the repo root."""
    for candidate in (root / reference, root / 'verification' / reference):
        if candidate.is_file():
            return candidate
    return None


def load_manifest(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data.get('files'), list):
        raise ValueError(f'{path}: manifest has no files list')
    return data


def verify(root, manifest_path, check_evidence=False):
    """Return a report dict; report['ok'] is True when every check passed."""
    root = Path(root)
    manifest_path = Path(manifest_path)
    manifest = load_manifest(manifest_path)
    snapshot = manifest_path.parent

    missing = []
    corrupt = []
    size_mismatch = []
    checked = 0
    for record in manifest['files']:
        relative = record['source_path']
        copy = snapshot / relative
        if not copy.is_file():
            missing.append(relative)
            continue
        actual = sha256_file(copy)
        checked += 1
        if actual != record['sha256']:
            corrupt.append({'source_path': relative, 'expected': record['sha256'], 'actual': actual})
            continue
        if 'bytes' in record and copy.stat().st_size != record['bytes']:
            size_mismatch.append(relative)

    evidence_missing = []
    evidence_absent = []
    evidence_checked = 0
    if check_evidence:
        cache = {}
        for record in manifest['files']:
            if record['pin_kind'] not in ('hard', 'both'):
                continue
            evidence_checked += 1
            references = record.get('evidence_refs') or []
            found = False
            for reference in references:
                if reference not in cache:
                    path = resolve_evidence(root, reference)
                    cache[reference] = None if path is None else HEX64.findall(
                        path.read_text(encoding='utf-8', errors='replace').lower())
                hashes = cache[reference]
                if hashes is None:
                    evidence_missing.append(reference)
                    continue
                if record['sha256'] in hashes:
                    found = True
                    break
            if not found:
                evidence_absent.append({
                    'source_path': record['source_path'],
                    'sha256': record['sha256'],
                    'evidence_refs': references,
                })

    ok = not (missing or corrupt or size_mismatch or evidence_missing or evidence_absent)
    return {
        'ok': ok,
        'manifest': str(manifest_path),
        'snapshot': str(snapshot),
        'declared_total': manifest.get('counts', {}).get('total'),
        'checked': checked,
        'missing': missing,
        'corrupt': corrupt,
        'size_mismatch': size_mismatch,
        'evidence_checked': evidence_checked,
        'evidence_missing': sorted(set(evidence_missing)),
        'evidence_absent': evidence_absent,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description='Verify the frozen evidence source snapshot.')
    parser.add_argument('--root', default=str(DEFAULT_ROOT), help='project root')
    parser.add_argument('--manifest', help=f'default: {DEFAULT_SNAPSHOT}/manifest.json')
    parser.add_argument('--evidence', action='store_true',
                        help='also require hard-pinned hashes to appear in their evidence files')
    parser.add_argument('--json', action='store_true', help='print the report as JSON')
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    manifest_path = Path(args.manifest) if args.manifest else root / DEFAULT_SNAPSHOT / 'manifest.json'
    report = verify(root, manifest_path, check_evidence=args.evidence)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(f"manifest: {report['manifest']}")
        print(f"files checked: {report['checked']}")
        for label, key in (('missing copies', 'missing'), ('sha256 mismatches', 'corrupt'),
                           ('size mismatches', 'size_mismatch')):
            for item in report[key]:
                print(f'  {label}: {item}')
        if args.evidence:
            print(f"hard-pinned entries evidence-checked: {report['evidence_checked']}")
            for item in report['evidence_missing']:
                print(f'  evidence file missing: {item}')
            for item in report['evidence_absent']:
                print(f"  hash absent from evidence: {item['source_path']}")
        print('PASS' if report['ok'] else 'FAIL')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
