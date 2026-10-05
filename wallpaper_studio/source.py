"""Read-only discovery and verified, isolated project staging.

Steam VDF discovery is adapted from wallpaper-engine-exporter v0.4.1
(MIT; its license is distributed in THIRD_PARTY_NOTICES).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .models import WallpaperEntry


class CancelledError(RuntimeError):
    pass


def check_cancel(cancel) -> None:
    if cancel is not None and cancel.is_set():
        raise CancelledError('任务已取消')


def run_tool(command, cancel=None, cwd=None, timeout=None) -> str:
    """Run an owned subprocess; terminate it on cancellation and propagate errors."""
    check_cancel(cancel)
    with tempfile.TemporaryFile() as log:
        started = time.monotonic()
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=cwd,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            while process.poll() is None:
                check_cancel(cancel)
                if timeout is not None and time.monotonic() - started >= timeout:
                    raise RuntimeError(f'Owned tool timeout after {timeout} seconds')
                time.sleep(0.05)
            log.seek(0)
            output = log.read().decode('utf-8', errors='replace')
            if process.returncode:
                raise RuntimeError(f'Tool exited {process.returncode}: {output[-8000:]}')
            return output
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _no_links(path: Path) -> None:
    for part in (path, *path.parents):
        if _is_link(part):
            raise ValueError(f"Source contains a link/junction: {part}")


def project_root(source: Path) -> Path:
    source = Path(source).absolute()
    _no_links(source)
    if not source.exists():
        raise FileNotFoundError(source)
    return source if source.is_dir() else source.parent


def _loose_media(source: Path) -> bool:
    source = Path(source)
    return (source.is_file() and not (source.parent / 'project.json').exists()
            and source.suffix.lower() in {'.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.gif', '.png', '.jpg', '.jpeg', '.webp'})


def assert_output_outside_source(source: Path, output: Path) -> None:
    root = Path(source).resolve() if _loose_media(source) else project_root(source).resolve()
    output = Path(output).resolve()
    if output == root or root in output.parents:
        raise ValueError("Output/workspace must be outside the source project")


def hash_manifest(root: Path, cancel=None) -> dict[str, str]:
    check_cancel(cancel)
    selected = Path(root).absolute() if _loose_media(root) else None
    root = project_root(root)
    manifest = {}
    for path in ([selected] if selected is not None else root.rglob('*')):
        check_cancel(cancel)
        if _is_link(path):
            raise ValueError(f"Source contains a link/junction: {path}")
        if path.is_file():
            digest = hashlib.sha256()
            with path.open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    check_cancel(cancel)
                    digest.update(chunk)
            manifest[path.relative_to(root).as_posix()] = digest.hexdigest()
    return dict(sorted(manifest.items()))


def verify_manifest(root: Path, expected: dict[str, str], cancel=None) -> None:
    if hash_manifest(root, cancel) != expected:
        raise RuntimeError("Project manifest verification failed")


def stage_project(source: Path, work_root: Path, cancel=None) -> Path:
    check_cancel(cancel)
    _no_links(Path(work_root).absolute())
    root = project_root(source)
    assert_output_outside_source(source, work_root)
    expected = hash_manifest(source, cancel)
    work_root = Path(work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    job = Path(tempfile.mkdtemp(prefix='job-', dir=work_root))
    staged = job / 'project'
    def copy_file(source_file, target_file):
        check_cancel(cancel)
        with open(source_file, 'rb') as reader, open(target_file, 'wb') as writer:
            for chunk in iter(lambda: reader.read(1024 * 1024), b''):
                check_cancel(cancel)
                writer.write(chunk)
        shutil.copystat(source_file, target_file)
        return target_file
    try:
        if _loose_media(source):
            staged.mkdir()
            copy_file(source, staged / Path(source).name)
        else:
            shutil.copytree(root, staged, symlinks=True, copy_function=copy_file)
        verify_manifest(staged, expected, cancel)
        verify_manifest(source, expected, cancel)
        (job / 'source-manifest.json').write_text(json.dumps(expected, indent=2), encoding='utf-8')
        return staged
    except Exception:
        shutil.rmtree(job)
        raise


def _vdf_object(tokens, position):
    result = []
    while position < len(tokens):
        if tokens[position] == '}':
            return result, position + 1
        key = tokens[position]
        position += 1
        if position >= len(tokens):
            break
        if tokens[position] == '{':
            value, position = _vdf_object(tokens, position + 1)
        else:
            value = tokens[position]
            position += 1
        result.append((key, value))
    return result, position


def parse_libraryfolders(text: str) -> list[Path]:
    tokens = [quoted or brace for quoted, brace in re.findall(r'"((?:\\.|[^"\\])*)"|([{}])', text)]
    if '{' not in tokens:
        return []
    root, _ = _vdf_object(tokens, tokens.index('{') + 1)
    paths = []
    for key, value in root:
        if not key.isdigit():
            continue
        if isinstance(value, list):
            value = next((v for k, v in value if k.casefold() == 'path'), None)
        if isinstance(value, str):
            paths.append(Path(value.replace('\\\\', '\\')))
    return list(dict.fromkeys(paths))


def steam_libraries() -> list[Path]:
    roots = [Path(os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')) / 'Steam',
             Path(os.environ.get('PROGRAMFILES', r'C:\Program Files')) / 'Steam']
    try:
        import winreg
        for hive, name, field in [(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                                  (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath')]:
            try:
                with winreg.OpenKey(hive, name) as key:
                    roots.insert(0, Path(winreg.QueryValueEx(key, field)[0]))
            except OSError:
                pass
    except ImportError:
        pass
    libraries = []
    for root in roots:
        if root.is_dir():
            libraries.append(root)
            vdf = root / 'steamapps/libraryfolders.vdf'
            if vdf.is_file():
                libraries.extend(parse_libraryfolders(vdf.read_text(encoding='utf-8', errors='replace')))
    return list(dict.fromkeys(libraries))


def engine_path() -> Path | None:
    for root in steam_libraries():
        for exe in ('wallpaper64.exe', 'wallpaper32.exe'):
            candidate = root / 'steamapps/common/wallpaper_engine' / exe
            if candidate.is_file():
                return candidate
    return None


def runtime_tool(name: str) -> Path:
    roots = [Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))]
    for root in roots:
        path = root / 'tools' / name
        if path.is_file():
            return path
    raise FileNotFoundError(f"Bundled tool missing: tools/{name}")


def _project_path(root: Path, field) -> Path | None:
    if not isinstance(field, str) or not field:
        return None
    path = Path(field)
    if path.is_absolute() or '..' in path.parts or path.drive or ':' in field or any(p.endswith((' ', '.')) for p in field.replace('\\', '/').split('/')):
        raise ValueError('Project path traversal')
    result = root / path
    _no_links(result)
    if root.resolve() not in result.resolve().parents:
        raise ValueError('Project path traversal')
    return result if result.is_file() else None


def normalize_library_root(root: Path) -> Path:
    root = Path(root).expanduser().absolute()
    for suffix in ('steamapps/workshop/content/431960', 'workshop/content/431960', 'content/431960', '431960'):
        candidate = root / suffix
        if candidate.is_dir():
            return candidate
    return root


def discover_library(root=None) -> list[WallpaperEntry]:
    roots = [normalize_library_root(root)] if root is not None else [p / 'steamapps/workshop/content/431960' for p in steam_libraries()]
    entries = []
    for library in roots:
        if not library.is_dir() or _is_link(library):
            continue
        candidates = [library] if (library / 'project.json').is_file() else list(library.iterdir())
        for project in candidates:
            if not project.is_dir() or _is_link(project):
                continue
            try:
                metadata = json.loads((project / 'project.json').read_text(encoding='utf-8-sig'))
                kind = str(metadata.get('type', '')).lower()
                if kind not in {'scene', 'video', 'web'}:
                    continue
                main = _project_path(project, metadata.get('file'))
                if main is None and kind == 'scene' and (project / 'scene.pkg').is_file():
                    _no_links(project / 'scene.pkg')
                    main = project / 'project.json'
                if main is None:
                    continue
                preview = _project_path(project, metadata.get('preview'))
                tags = metadata.get('tags', [])
                if not isinstance(tags, list): tags = []
                entries.append(WallpaperEntry(project, str(metadata.get('title', project.name)), kind, preview, main,
                                              tuple(str(t) for t in tags), str(metadata.get('contentrating', 'Unknown'))))
            except (OSError, ValueError, TypeError):
                continue
    return sorted(entries, key=lambda entry: entry.title.casefold())


def validate_package(package: Path) -> list[str]:
    """Validate the native RePKG index before any archive member is written."""
    size = package.stat().st_size
    with package.open('rb') as handle:
        def integer():
            data = handle.read(4)
            if len(data) != 4:
                raise ValueError('Truncated package index')
            return struct.unpack('<i', data)[0]
        def string(limit):
            length = integer()
            if not 0 < length <= limit:
                raise ValueError('Invalid package string length')
            data = handle.read(length)
            if len(data) != length:
                raise ValueError('Truncated package string')
            return data.decode('utf-8')
        if not re.fullmatch(r'PKGV\d{4}', string(32)):
            raise ValueError('Unsupported package signature')
        count = integer()
        if not 0 <= count <= 1_000_000:
            raise ValueError('Invalid package entry count')
        entries = []
        for _ in range(count):
            name = string(255).replace('\\', '/')
            path = Path(name)
            if path.is_absolute() or path.drive or ':' in name or '\x00' in name or any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in name.split('/')):
                raise ValueError(f'Unsafe package path: {name}')
            offset, length = integer(), integer()
            if offset < 0 or length < 0:
                raise ValueError('Invalid package range')
            entries.append((name, offset, length))
        start = handle.tell()
        if any(start + offset + length > size for _, offset, length in entries):
            raise ValueError('Truncated package data')
        return [name for name, _, _ in entries]


def extract_resources(source: Path, output: Path, cancel=None, progress=None) -> Path:
    check_cancel(cancel)
    output = Path(output).absolute()
    assert_output_outside_source(source, output)
    _no_links(output)
    if output.exists():
        raise FileExistsError(f'Resource output already exists: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    expected = hash_manifest(source, cancel)
    with tempfile.TemporaryDirectory(prefix='resources-job-', dir=output.parent) as workspace:
        staged = stage_project(source, Path(workspace), cancel)
        packages = sorted(staged.rglob('*.pkg'))
        for package in packages:
            validate_package(package)
        # Extraction changes only the verified copy, never the original project.
        destination = staged
        try:
            for index, package in enumerate(packages):
                check_cancel(cancel)
                if progress:
                    progress(int(index * 90 / len(packages)), f'解包 {package.name}')
                target = destination / package.relative_to(staged).parent
                run_tool([str(runtime_tool('RePKG.exe')), 'extract', str(package), '-o', str(target), '--overwrite'], cancel, cwd=workspace)
            check_cancel(cancel)
            hash_manifest(destination, cancel)  # rejects links/junctions created by extraction
            verify_manifest(source, expected)
            destination.rename(output)
        finally:
            verify_manifest(source, expected)
    if progress:
        progress(100, '资源导出完成')
    return output
