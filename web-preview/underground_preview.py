"""Bounded explicit underground geometry generation and saved-package reads."""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'verification/natural-river-network'
DEFAULT = BASE / 'underground-river-v1-20261006-01/index.json'
MAX_BYTES = 64 * 1024 ** 2
MAX_SECONDS = 60
LOCK = threading.Lock()
DEFAULT_PARAMETERS = {'seed': 17, 'lateral_amplitude_m': 1.0, 'width_scale': 1.05, 'roof_variation_m': 0.2}

class GenerationBusy(RuntimeError):
    pass

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate request/record key: ' + key)
        result[key] = value
    return result

def reject_constant(value):
    raise ValueError('nonfinite JSON constant: ' + value)

def identity(record):
    payload = json.dumps({key: value for key, value in record.items() if key != 'identity_sha256'}, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()

def read_record(path):
    path = Path(path).resolve(strict=True)
    if not path.is_relative_to(BASE) or path.stat().st_size > MAX_BYTES:
        raise ValueError('underground package path/size outside allowed scope')
    payload = path.read_bytes()
    record = json.loads(payload, object_pairs_hook=unique_object, parse_constant=reject_constant)
    if not isinstance(record, dict) or record.get('identity_sha256') != identity(record):
        raise ValueError('underground package content identity mismatch')
    return (record, hashlib.sha256(payload).hexdigest())

def saved_case(index_path=DEFAULT):
    index_path = Path(index_path).resolve(strict=True)
    index, _ = read_record(index_path)
    if index.get('schema') != 'td-underground-river-preparation-v1' or index.get('status') != 'geometry_checked':
        raise ValueError('refused or unknown underground preparation')
    pin = index['preview']
    path = Path(pin['path']).resolve(strict=True)
    if path.parent != index_path.parent or path.name != 'preview.json':
        raise ValueError('preview must belong to its immutable package')
    record, sha = read_record(path)
    if sha != pin['sha256'] or record['identity_sha256'] != pin['identity_sha256']:
        raise ValueError('underground preview pin mismatch')
    if record.get('schema') != 'td-underground-river-preview-v1' or record.get('status') != 'geometry_checked':
        raise ValueError('refused or unknown underground preview')
    if record.get('source_pins') != index.get('parents') or record.get('parameters') != index.get('parameters'):
        raise ValueError('underground preparation/preview provenance differs')
    for pin in record['source_pins'].values():
        source = Path(pin['path']).resolve(strict=True)
        if not source.is_relative_to(BASE) or source.stat().st_size > MAX_BYTES:
            raise ValueError('underground source outside bounded scope')
        if hashlib.sha256(source.read_bytes()).hexdigest() != pin['sha256']:
            raise ValueError('underground source pin changed')
    flags = record.get('capabilities', {})
    if record.get('water', 'missing') is not None or any((flags.get(name) is not False for name in ('hydraulic_solved', 'full_network_verified', 'natural_outlet_certified'))):
        raise ValueError('underground preview capability boundary differs')
    return record

def parameters(body):
    if not isinstance(body, dict) or set(body) != set(DEFAULT_PARAMETERS):
        raise ValueError('only seed, lateral_amplitude_m, width_scale, roof_variation_m are accepted')
    if type(body['seed']) is not int or not 0 <= body['seed'] <= 2 ** 32 - 1:
        raise ValueError('seed must be a uint32 integer')
    for name, lower, upper in (('lateral_amplitude_m', 0.0, 3.0), ('width_scale', 0.8, 1.2), ('roof_variation_m', 0.0, 0.5)):
        value = body[name]
        if type(value) not in (int, float) or not math.isfinite(value) or (not lower <= value <= upper):
            raise ValueError(name + ': parameter outside finite v1 bounds')
    return body

def generate(body):
    recipe = parameters(body)
    if not LOCK.acquire(blocking=False):
        raise GenerationBusy('another underground geometry generation is running')
    try:
        directory = BASE / ('underground-river-v1-preview-' + uuid.uuid4().hex)
        command = [sys.executable, str(ROOT / 'tools/prepare_underground_rivers.py'), '--output', str(directory)]
        for name, value in recipe.items():
            command.extend(('--' + name.replace('_', '-'), str(value)))
        environment = dict(os.environ)
        dependencies = ROOT / '.scratch/hybrid-river-network/python-deps'
        if dependencies.is_dir():
            environment['PYTHONPATH'] = str(dependencies) + os.pathsep + environment.get('PYTHONPATH', '')
        completed = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=MAX_SECONDS, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False)
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or 'geometry generation refused')[-1600:]
            raise ValueError(message)
        return saved_case(directory / 'index.json')
    finally:
        LOCK.release()
