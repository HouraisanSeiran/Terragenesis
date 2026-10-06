"""Install the bundled Terrain Diffusion service under a Minecraft game directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile


ASSETS = Path(__file__).resolve().parents[1] / "bootstrap-assets"
PIP_URL = "https://files.pythonhosted.org/packages/8a/6a/19e9fe04fca059ccf770861c7d5721ab4c2aebc539889e97c7977528a53b/pip-24.0-py3-none-any.whl"
PIP_SHA256 = "ba0d021a166865d2265246961bec0152ff124de910c5cc39f1156ce3fa7c69dc"
PIP_BYTES = 2110226
TORCH_WHEELS = {
    "torch-2.9.1+cu126-cp311-cp311-win_amd64.whl": {
        "url": "https://download-r2.pytorch.org/whl/cu126/torch-2.9.1%2Bcu126-cp311-cp311-win_amd64.whl",
        "bytes": 2584537899,
        "sha256": "8afd366413aeb51a4732042719f168fae6f4c72326e59e9bdbe20a5c5be52418",
    },
    "torchvision-0.24.1+cu126-cp311-cp311-win_amd64.whl": {
        "url": "https://download-r2.pytorch.org/whl/cu126/torchvision-0.24.1%2Bcu126-cp311-cp311-win_amd64.whl",
        "bytes": 8526527,
        "sha256": "c855a39415d8a217cf6c488bcd29735ceefe33e49cb8afe6ebda44e6e30c106d",
    },
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def valid(path: Path, size: int, sha256: str) -> bool:
    return path.is_file() and path.stat().st_size == size and digest(path) == sha256


def download(url: str, path: Path, size: int, sha256: str) -> None:
    if valid(path, size, sha256):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    if size > 500_000_000 and sys.platform == "win32":
        download_large(url, path, size, sha256)
        return
    for attempt in range(5):
        offset = part.stat().st_size if part.exists() else 0
        if offset == size and digest(part) == sha256:
            part.replace(path)
            return
        if offset >= size:
            part.unlink()
            offset = 0
        headers = {"User-Agent": "Terragenesis-bootstrap/1"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        try:
            with urlopen(Request(url, headers=headers), timeout=45) as response:
                status = response.status
                if offset and (status != 206 or response.headers.get("Content-Range", "").split("/")[0] != f"bytes {offset}-{size - 1}"):
                    part.unlink(missing_ok=True)
                    raise IOError("Server did not honor the resume range")
                if not offset and status != 200:
                    raise IOError(f"Unexpected HTTP status {status}")
                with part.open("ab" if offset else "wb") as output:
                    shutil.copyfileobj(response, output, 1024 * 1024)
            if valid(part, size, sha256):
                part.replace(path)
                return
            if part.stat().st_size >= size:
                part.unlink()
            raise IOError(f"Size or SHA-256 mismatch for {path.name}")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            print(f"Download retry {attempt + 1}/5 for {path.name}: {exc}", flush=True)
            if attempt == 4:
                raise RuntimeError(f"Cannot download verified {path.name}") from exc
            time.sleep(min(2 ** attempt, 8))


def download_large(url: str, path: Path, size: int, sha256: str) -> None:
    if shutil.which("curl.exe") is None:
        raise RuntimeError("Windows curl.exe is required for large dependency downloads")
    part = path.with_name(path.name + ".part")
    for attempt in range(5):
        if valid(part, size, sha256):
            part.replace(path)
            return
        if part.exists() and part.stat().st_size >= size:
            part.unlink()
        command = ["curl.exe", "--location", "--fail", "--show-error", "--silent",
                   "--connect-timeout", "20", "--speed-limit", "1024", "--speed-time", "30",
                   "--continue-at", "-", "--output", str(part), url]
        result = subprocess.run(command, check=False,
                                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        if result.returncode == 0 and valid(part, size, sha256):
            part.replace(path)
            return
        if result.returncode == 33 or (part.exists() and part.stat().st_size >= size):
            part.unlink(missing_ok=True)
        print(f"Large download retry {attempt + 1}/5 for {path.name}", flush=True)
        if attempt < 4:
            time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"Cannot download verified {path.name}")


def bootstrap_pip(home: Path) -> None:
    try:
        import pip  # noqa: F401
        return
    except ImportError:
        pass
    wheel = home / "runtime" / "downloads" / "pip-24.0-py3-none-any.whl"
    download(PIP_URL, wheel, PIP_BYTES, PIP_SHA256)
    site = home / "python" / "Lib" / "site-packages"
    site.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            relative = Path(member.filename)
            if relative.is_absolute() or ".." in relative.parts or ":" in member.filename:
                raise RuntimeError("Unsafe pip wheel member")
            target = site / relative
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)


def install_requirements(home: Path) -> None:
    lock = ASSETS / "requirements-lock.txt"
    if not lock.is_file():
        raise RuntimeError("Bundled dependency lock is missing")
    runtime = home / "runtime"
    for name in ("tmp", "pip-cache", "hf", "torch", "numba", "mpl"):
        (runtime / name).mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(TMP=str(runtime / "tmp"), TEMP=str(runtime / "tmp"),
               PIP_CACHE_DIR=str(runtime / "pip-cache"), HF_HOME=str(runtime / "hf"),
               TORCH_HOME=str(runtime / "torch"), NUMBA_CACHE_DIR=str(runtime / "numba"),
               MPLCONFIGDIR=str(runtime / "mpl"), PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1",
               PIP_CONFIG_FILE=os.devnull)
    command = [sys.executable, "-u", "-m", "pip", "--isolated", "install", "--disable-pip-version-check",
               "--only-binary=:all:", "--timeout", "45", "--retries", "3", "--index-url", "https://pypi.org/simple",
               "--cache-dir", str(runtime / "pip-cache"), "--no-user"]
    other_lock = runtime / "other-requirements.txt"
    lines = lock.read_text(encoding="utf-8").splitlines()
    other_lock.write_text("\n".join(line for line in lines if line and not line.startswith(("torch==", "torchvision=="))) + "\n", encoding="utf-8")
    wheels = []
    for name, expected in TORCH_WHEELS.items():
        wheel = runtime / "downloads" / name
        print(f"Verifying dependency {name}", flush=True)
        download(expected["url"], wheel, expected["bytes"], expected["sha256"])
        wheels.append(str(wheel))
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.run(command + ["--constraint", str(lock)] + wheels, check=True, env=env, creationflags=flags)
    subprocess.run(command + ["-r", str(other_lock)], check=True, env=env, creationflags=flags)


def install_upstream(home: Path) -> None:
    spec = json.loads((ASSETS / "upstream-manifest.json").read_text(encoding="utf-8"))
    source = ASSETS.parent / spec["source"]
    target = home / spec["source"]
    for name, expected in spec["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("Unsafe upstream path")
        bundled = source / relative
        if not valid(bundled, expected["bytes"], expected["sha256"]):
            raise RuntimeError(f"Bundled upstream file failed SHA-256: {name}")
        dest = target / relative
        if not valid(dest, expected["bytes"], expected["sha256"]):
            dest.parent.mkdir(parents=True, exist_ok=True)
            temporary = dest.with_name(dest.name + ".part")
            shutil.copyfile(bundled, temporary)
            temporary.replace(dest)
    upstream = {key: spec[key] for key in ("repository", "revision", "source", "inference_files")}
    path = home / "runtime" / "upstream.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(upstream, indent=2), encoding="utf-8")


def install_model(home: Path, local_source: Path | None = None) -> None:
    manifest_path = ASSETS / "model-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target = home / "models" / "terrain-diffusion-30m"
    for name, expected in manifest["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("Unsafe model path")
        destination = target / relative
        if local_source is not None and not valid(destination, expected["bytes"], expected["sha256"]):
            candidate = local_source / relative
            if valid(candidate, expected["bytes"], expected["sha256"]):
                destination.parent.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_name(destination.name + ".part")
                shutil.copyfile(candidate, temporary)
                temporary.replace(destination)
        url = f"{manifest['endpoint'].rstrip('/')}/{manifest['model']}/resolve/{manifest['revision']}/{relative.as_posix()}"
        print(f"Verifying model {name}", flush=True)
        download(url, destination, expected["bytes"], expected["sha256"])
    target.mkdir(parents=True, exist_ok=True)
    (target / "manifest.json").write_bytes(manifest_path.read_bytes())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--model-source", type=Path, help="Verified local model source for development installs")
    args = parser.parse_args()
    home = args.home.resolve()
    if sys.version_info[:2] != (3, 11) or sys.platform != "win32":
        raise RuntimeError("Bundled runtime requires Windows x64 Python 3.11")
    if Path(sys.executable).resolve() != (home / "python" / "python.exe").resolve():
        raise RuntimeError("Bootstrap must run with the bundled Python interpreter")
    bootstrap_pip(home)
    install_requirements(home)
    install_upstream(home)
    install_model(home, args.model_source)
    print("READY", flush=True)


if __name__ == "__main__":
    main()
