import json
from pathlib import Path

import pytest

from wallpaper_studio import source


def project(root, kind='scene', file='scene.pkg'):
    root.mkdir(parents=True)
    (root / 'project.json').write_text(json.dumps({'title': '测试', 'type': kind, 'file': file}), encoding='utf-8')
    (root / file).write_bytes(b'content')
    (root / 'nested').mkdir()
    (root / 'nested' / 'texture.bin').write_bytes(b'texture')
    return root


def test_stage_copies_entire_project_and_verifies_manifest(tmp_path):
    original = project(tmp_path / 'source')
    before = source.hash_manifest(original)
    staged = source.stage_project(original, tmp_path / 'jobs')
    assert staged != original
    assert source.hash_manifest(staged) == before
    (staged / 'nested' / 'texture.bin').write_bytes(b'changed')
    assert source.hash_manifest(original) == before


def test_stage_rejects_workspace_inside_source(tmp_path):
    original = project(tmp_path / 'source')
    with pytest.raises(ValueError, match='source'):
        source.stage_project(original, original / 'jobs')


def test_discovery_supports_scene_video_web_and_rejects_traversal(tmp_path):
    project(tmp_path / '1')
    project(tmp_path / '2', 'video', 'movie.mp4')
    project(tmp_path / '3', 'web', 'index.html')
    bad = tmp_path / 'bad'
    bad.mkdir()
    (bad / 'project.json').write_text(json.dumps({'type': 'scene', 'file': '../secret'}))
    entries = source.discover_library(tmp_path)
    assert {entry.kind for entry in entries} == {'scene', 'video', 'web'}
    assert all(entry.wallpaper_file.is_file() for entry in entries)


def test_hash_manifest_rejects_link_or_junction(tmp_path):
    original = project(tmp_path / 'source')
    try:
        (original / 'link').symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip('Windows symlink privilege unavailable')
    with pytest.raises(ValueError, match='link'):
        source.hash_manifest(original)


def test_manifest_detects_corrupt_copy(tmp_path):
    original = project(tmp_path / 'source')
    expected = source.hash_manifest(original)
    (original / 'scene.pkg').write_bytes(b'changed')
    with pytest.raises(RuntimeError, match='manifest'):
        source.verify_manifest(original, expected)


def test_parse_libraryfolders_handles_nested_apps(tmp_path):
    library = str(tmp_path).replace('\\', '\\\\')
    assert source.parse_libraryfolders('"libraryfolders" { "0" { "path" "' + library + '" "apps" { "431960" "1" } } }') == [tmp_path]


def test_package_validator_rejects_traversal_before_extraction(tmp_path):
    import struct
    def string(value):
        data = value.encode()
        return struct.pack('<i', len(data)) + data
    path = tmp_path / 'malicious.pkg'
    path.write_bytes(string('PKGV0005') + struct.pack('<i', 1) + string('../escape.txt') + struct.pack('<ii', 0, 1) + b'x')
    with pytest.raises(ValueError, match='path'):
        source.validate_package(path)


def test_package_validator_accepts_native_archive(tmp_path):
    import struct
    def string(value):
        data = value.encode()
        return struct.pack('<i', len(data)) + data
    path = tmp_path / 'scene.pkg'
    path.write_bytes(string('PKGV0005') + struct.pack('<i', 1) + string('materials/texture.tex') + struct.pack('<ii', 0, 1) + b'x')
    assert source.validate_package(path) == ['materials/texture.tex']


def test_resource_export_copies_unpacked_project_without_changing_source(tmp_path):
    original = project(tmp_path / 'source', 'web', 'index.html')
    before = source.hash_manifest(original)
    result = source.extract_resources(original, tmp_path / 'resources', None, None)
    assert (result / 'index.html').read_bytes() == b'content'
    assert source.hash_manifest(original) == before


def test_discovery_keeps_packed_scene_when_declared_json_is_in_pkg(tmp_path):
    root = project(tmp_path / 'scene')
    (root / 'project.json').write_text(json.dumps({'type':'scene', 'file':'scene.json', 'title':'packed'}))
    entries = source.discover_library(tmp_path)
    assert len(entries) == 1
    assert entries[0].wallpaper_file == root / 'project.json'


def test_package_validator_rejects_windows_normalized_traversal(tmp_path):
    import struct
    def string(value):
        data = value.encode()
        return struct.pack('<i', len(data)) + data
    path = tmp_path / 'malicious.pkg'
    path.write_bytes(string('PKGV0005') + struct.pack('<i', 1) + string('.. /escape.txt') + struct.pack('<ii', 0, 1) + b'x')
    with pytest.raises(ValueError, match='path'):
        source.validate_package(path)


def test_loose_video_staging_does_not_copy_unrelated_downloads(tmp_path):
    media = tmp_path / 'movie.mp4'
    media.write_bytes(b'video')
    (tmp_path / 'unrelated.bin').write_bytes(b'unrelated')
    staged = source.stage_project(media, tmp_path / 'jobs')
    assert (staged / media.name).read_bytes() == b'video'
    assert not (staged / 'unrelated.bin').exists()
    assert set(source.hash_manifest(media)) == {'movie.mp4'}


def test_loose_video_allows_sibling_output(tmp_path):
    media = tmp_path / 'movie.mp4'
    media.write_bytes(b'video')
    source.assert_output_outside_source(media, tmp_path / 'edited.mp4')
    with pytest.raises(ValueError):
        source.assert_output_outside_source(media, media)


def test_hash_manifest_rejects_windows_junction_without_following(tmp_path):
    import os
    import subprocess
    if os.name != 'nt':
        pytest.skip('Windows junction test')
    original = project(tmp_path / 'source')
    target = tmp_path / 'outside'
    target.mkdir()
    result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(original / 'junction'), str(target)], capture_output=True)
    assert result.returncode == 0, result.stderr
    with pytest.raises(ValueError, match='link'):
        source.hash_manifest(original)


def test_owned_tool_timeout_terminates_process():
    import sys
    import time
    started = time.monotonic()
    with pytest.raises(RuntimeError, match='timeout'):
        source.run_tool([sys.executable, '-c', 'import time; time.sleep(60)'], timeout=.1)
    assert time.monotonic() - started < 5


def test_cancelled_staging_and_manifest_do_not_start_work(tmp_path):
    import threading
    original = project(tmp_path / 'source')
    event = threading.Event()
    event.set()
    with pytest.raises(source.CancelledError):
        source.hash_manifest(original, cancel=event)
    with pytest.raises(source.CancelledError):
        source.stage_project(original, tmp_path / 'jobs', cancel=event)
    assert not (tmp_path / 'jobs').exists()


def test_staging_rejects_junction_workspace(tmp_path):
    import os
    import subprocess
    if os.name != 'nt':
        pytest.skip('Windows junction test')
    original = project(tmp_path / 'source')
    target = tmp_path / 'outside'
    target.mkdir()
    link = tmp_path / 'jobs'
    assert subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True).returncode == 0
    with pytest.raises(ValueError, match='link'):
        source.stage_project(original, link)
    assert list(target.iterdir()) == []
