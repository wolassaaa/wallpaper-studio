"""Live Photo pair writer. Structural validation is not device acceptance.

Format references: Apple's QuickTime File Format timed metadata sample descriptions,
metadata key table/keyd/dtyp/sample data format; ExifTool Apple tag 0x0011.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import struct
import uuid
import zipfile

U32 = lambda *v: struct.pack('>' + 'I' * len(v), *v)
KEY = b'com.apple.quicktime.still-image-time'
IDENTIFIER_KEY = b'com.apple.quicktime.content.identifier'
MATRIX = U32(65536, 0, 0, 0, 65536, 0, 0, 0, 1073741824)


def atom(kind, payload=b''):
    if isinstance(kind, str):
        kind = kind.encode('ascii')
    return U32(len(payload) + 8) + kind + payload


def full(kind, payload=b'', flags=0):
    return atom(kind, U32(flags) + payload)


def atoms(data, start=0, end=None):
    """Strict atom parser; returns (type, start, payload start, end)."""
    end = len(data) if end is None else end
    while start < end:
        if start + 8 > end:
            raise ValueError('Truncated MOV atom')
        size, kind = struct.unpack_from('>I4s', data, start)
        header = 8
        if size == 1:
            if start + 16 > end:
                raise ValueError('Truncated extended atom')
            size = struct.unpack_from('>Q', data, start + 8)[0]
            header = 16
        elif size == 0:
            size = end - start
        if size < header or start + size > end:
            raise ValueError('Invalid MOV atom size')
        yield kind, start, start + header, start + size
        start += size


def child(data, start, end, kind):
    for k, a, p, z in atoms(data, start, end):
        if k == kind:
            return p, z
    raise ValueError('Missing MOV atom ' + repr(kind))


def apple_makernote(identifier):
    value = identifier.encode('ascii') + b'\0'
    # Apple IFD is big endian, begins at offset 14; pointers are maker-note-relative.
    return (b'Apple iOS\0\0\x01MM' + struct.pack('>H', 1)
            + struct.pack('>HHII', 17, 2, len(value), 32) + U32(0) + value)


def write_photo(path, identifier):
    from PIL import Image
    with Image.open(path) as image:
        exif = Image.Exif()
        exif[531] = 1  # YCbCrPositioning
        exif[34665] = {37500: apple_makernote(identifier), 36864: b'0232',
                       37121: b'\x01\x02\x03\x00', 40961: 1,
                       40962: image.width, 40963: image.height}
        payload = bytearray(exif.tobytes())
        # Pillow infers BYTE for unknown binary EXIF fields. The EXIF standard
        # requires UNDEFINED for MakerNote and ComponentsConfiguration.
        endian = '<' if payload[6:8] == b'II' else '>'
        first = 6 + struct.unpack_from(endian+'I', payload, 10)[0]
        count = struct.unpack_from(endian+'H', payload, first)[0]
        for i in range(count):
            entry = first + 2 + i*12
            if struct.unpack_from(endian+'H', payload, entry)[0] == 34665:
                nested = 6 + struct.unpack_from(endian+'I', payload, entry+8)[0]
                for j in range(struct.unpack_from(endian+'H', payload, nested)[0]):
                    address = nested + 2 + j*12
                    if struct.unpack_from(endian+'H', payload, address)[0] in (37500,37121):
                        struct.pack_into(endian+'H', payload, address+2, 7)
        image.convert('RGB').save(path, 'JPEG', quality=95, exif=bytes(payload))


def clip_window(duration, start, end, cover):
    end = duration if end is None else end
    if not 0 <= start < end <= duration + 1e-6:
        raise ValueError('Live Photo interval is outside source duration')
    if not start <= cover < end:
        raise ValueError('Cover must be within the selected source interval')
    if end - start < 3 - 1e-6:
        raise ValueError('Live Photo needs at least three seconds; source is never looped')
    left = max(start, min(cover - 1.5, end - 3))
    return left, left + 3


def _movie_metadata(identifier):
    handler = full('hdlr', U32(0) + b'mdta' + b'\0' * 12 + b'\0')
    keys = full('keys', U32(1) + atom('mdta', IDENTIFIER_KEY))
    value = atom('data', U32(1, 0) + identifier.encode('ascii'))
    return atom('meta', handler + keys + atom('ilst', atom(U32(1), value)))


def _metadata_track(track_id, video_id, movie_scale, movie_duration, cover, fps, offset):
    scale = 60000
    duration = round(movie_duration / movie_scale * scale)
    marker = min(round(cover * scale), duration - 1)
    width = min(max(1, round(scale / fps)), duration - marker)
    samples, deltas = [], []
    if marker:
        samples.append(atom(U32(0)))
        deltas.append(marker)
    # LimitPoint's AVFoundation reference sets the int8 marker to zero.
    # Camera-origin resources can also carry -1 (ExifTool's observed format).
    # The sample PTS, rather than the sentinel value, marks the cover.
    samples.append(atom(U32(1), b'\x00'))
    deltas.append(width)
    if marker + width < duration:
        samples.append(atom(U32(0)))
        deltas.append(duration - marker - width)
    tkhd = full('tkhd', U32(0, 0, track_id, 0, movie_duration) + b'\0' * 8
                + b'\0' * 8 + MATRIX + U32(0, 0), flags=3)
    mdhd = full('mdhd', U32(0, 0, scale, duration) + struct.pack('>HH', 0x55c4, 0))
    hdlr = full('hdlr', U32(0) + b'mdta' + b'\0' * 12 + b'Core Media Metadata\0')
    # Timed metadata keys has no version/count (unlike movie-level meta keys).
    key = atom(U32(1), atom('keyd', b'mdta' + KEY) + atom('dtyp', U32(0, 65)))
    entry = atom('mebx', b'\0' * 6 + struct.pack('>H', 1) + atom('keys', key))
    stsd = full('stsd', U32(1) + entry)
    stts = full('stts', U32(len(deltas)) + b''.join(U32(1, d) for d in deltas))
    stsc = full('stsc', U32(1, 1, len(samples), 1))
    stsz = full('stsz', U32(0, len(samples)) + b''.join(U32(len(s)) for s in samples))
    co64 = full('co64', U32(1) + struct.pack('>Q', offset))
    stbl = atom('stbl', stsd + stts + stsc + stsz + co64)
    dinf = atom('dinf', full('dref', U32(1) + full('url ', flags=1)))
    gmhd = atom('gmhd', full('gmin', struct.pack('>HHHHHH', 64, 32768, 32768, 32768, 0, 0)))
    mdia = atom('mdia', mdhd + hdlr + atom('minf', gmhd + dinf + stbl))
    return atom('trak', tkhd + atom('tref', atom('cdsc', U32(video_id))) + mdia), b''.join(samples)


def write_motion_metadata(path, identifier, cover, fps):
    path = Path(path)
    data = path.read_bytes()
    moovs = [x for x in atoms(data) if x[0] == b'moov']
    if len(moovs) != 1:
        raise ValueError('Expected one nonfragmented movie')
    _, a, p, z = moovs[0]
    if any(k == b'moof' for k, *_ in atoms(data)):
        raise ValueError('Fragmented MOV is not supported')
    mp, mz = child(data, p, z, b'mvhd')
    if data[mp] != 0:
        raise ValueError('MOV version-1 movie header is not supported')
    movie_scale, duration = struct.unpack_from('>II', data, mp + 12)
    ids = []
    video_id = None
    for k, _, tp, tz in atoms(data, p, z):
        if k == b'trak':
            hp, _ = child(data, tp, tz, b'tkhd')
            if data[hp] != 0:
                raise ValueError('MOV version-1 track header is not supported')
            track_id = struct.unpack_from('>I', data, hp + 12)[0]
            ids.append(track_id)
            dp, dz = child(data, tp, tz, b'mdia')
            hp, _ = child(data, dp, dz, b'hdlr')
            if data[hp + 8:hp + 12] == b'vide':
                video_id = track_id
    if video_id is None:
        raise ValueError('Movie has no video track')
    if not 0 <= cover < duration / movie_scale:
        raise ValueError('Cover outside exported movie')
    track_id = max(ids) + 1
    track, sample = _metadata_track(track_id, video_id, movie_scale, duration,
                                    cover, fps, len(data) + 8)
    content = bytearray(data[p:z])
    # mvhd next_track_ID is the final 32-bit field.
    struct.pack_into('>I', content, mz - p - 4, track_id + 1)
    new_moov = atom('moov', bytes(content) + _movie_metadata(identifier) + track)
    # Keep every existing stco/co64 offset unchanged, including fast-start input.
    original = bytearray(data)
    original[a + 4:a + 8] = b'free'
    path.write_bytes(bytes(original) + atom('mdat', sample) + new_moov)


def _photo_identifier(path):
    from PIL import Image
    with Image.open(path) as image:
        m = image.getexif().get_ifd(34665).get(37500, b'')
    if m[:14] != b'Apple iOS\0\0\x01MM':
        raise ValueError('Missing Apple MakerNote')
    count = _field(m, 0, len(m), '>H', 14)[0]
    if 16+12*count+4 > len(m):
        raise ValueError('Truncated Apple MakerNote directory')
    for i in range(count):
        tag, typ, length, pointer = _field(m, 0, len(m), '>HHII', 16+12*i)
        if tag == 17 and typ == 2:
            if not length or pointer+length > len(m) or m[pointer+length-1] != 0:
                raise ValueError('Invalid Apple ContentIdentifier offset/length')
            try:
                return m[pointer:pointer+length-1].decode('ascii')
            except UnicodeError as exc:
                raise ValueError('Invalid Apple ContentIdentifier encoding') from exc
    raise ValueError('Missing Apple ContentIdentifier tag 17')


def _field(data, start, end, fmt, relative=0):
    position = start + relative
    if relative < 0 or end > len(data) or position + struct.calcsize(fmt) > end:
        raise ValueError('Truncated MOV atom field')
    return struct.unpack_from(fmt, data, position)


def _header(data, start, end, minimum):
    if _field(data,start,end,'>B')[0] != 0 or end-start < minimum:
        raise ValueError('Unsupported version or truncated MOV header')


def _check_video_samples(data, sp, sz, descriptions):
    cp,cz = child(data,sp,sz,b'stsz')
    _header(data,cp,cz,12)
    fixed,n = _field(data,cp,cz,'>II',4)
    if not 1 <= n <= 1000000 or cz-cp != (12 if fixed else 12+4*n):
        raise ValueError('Invalid video sample size table')
    sizes = [fixed]*n if fixed else list(_field(data,cp,cz,'>'+'I'*n,12))
    if any(size == 0 for size in sizes):
        raise ValueError('Video has empty samples')
    offsets = [(k,p,z) for k,_,p,z in atoms(data,sp,sz) if k in (b'stco',b'co64')]
    if len(offsets) != 1:
        raise ValueError('Expected one video chunk offset table')
    kind,cp,cz = offsets[0]
    _header(data,cp,cz,8)
    chunks = _field(data,cp,cz,'>I',4)[0]
    width,fmt = (4,'I') if kind == b'stco' else (8,'Q')
    if not 1 <= chunks <= n or cz-cp != 8+width*chunks:
        raise ValueError('Invalid video chunk offset table')
    offsets = _field(data,cp,cz,'>'+fmt*chunks,8)
    cp,cz = child(data,sp,sz,b'stsc')
    _header(data,cp,cz,8)
    count = _field(data,cp,cz,'>I',4)[0]
    if not 1 <= count <= chunks or cz-cp != 8+12*count:
        raise ValueError('Invalid video chunk sample table')
    mappings = [_field(data,cp,cz,'>III',8+12*i) for i in range(count)]
    if mappings[0][0] != 1:
        raise ValueError('Video chunks must start at one')
    for i,(first,per_chunk,description) in enumerate(mappings):
        if not 1 <= first <= chunks or not per_chunk or not 1 <= description <= descriptions or (i and first <= mappings[i-1][0]):
            raise ValueError('Invalid video chunk sample mapping')
    mdats = [(p,z) for k,_,p,z in atoms(data) if k == b'mdat']
    consumed,index = 0,0
    for chunk,offset in enumerate(offsets,1):
        while index+1 < count and mappings[index+1][0] <= chunk:
            index += 1
        samples = mappings[index][1]
        if consumed+samples > n:
            raise ValueError('Video chunk has excess samples')
        length = sum(sizes[consumed:consumed+samples])
        if not any(p <= offset and offset+length <= z for p,z in mdats):
            raise ValueError('Video chunk points outside mdat')
        consumed += samples
    if consumed != n:
        raise ValueError('Video chunk tables omit samples')


def _check_tracks(data, p, z):
    mp,mz = child(data,p,z,b'mvhd')
    _header(data,mp,mz,100)
    movie_scale,movie_duration = _field(data,mp,mz,'>II',12)
    if not movie_scale or not movie_duration:
        raise ValueError('Invalid movie timescale/duration')
    track_ids, video_ids, metadata_tracks = set(), set(), []
    for kind,_,tp,tz in atoms(data,p,z):
        if kind != b'trak':
            continue
        hp,hz = child(data,tp,tz,b'tkhd')
        _header(data,hp,hz,84)
        track_id = _field(data,hp,hz,'>I',12)[0]
        track_duration = _field(data,hp,hz,'>I',20)[0]
        if not track_id or track_id in track_ids:
            raise ValueError('Invalid or duplicate track ID')
        track_ids.add(track_id)
        if not 0 < track_duration <= movie_duration:
            raise ValueError('Track duration lies outside movie')
        dp,dz = child(data,tp,tz,b'mdia')
        hp,hz = child(data,dp,dz,b'hdlr')
        _header(data,hp,hz,24)
        handler = _field(data,hp,hz,'>4s',8)[0]
        hp,hz = child(data,dp,dz,b'mdhd')
        _header(data,hp,hz,24)
        scale,duration = _field(data,hp,hz,'>II',12)
        if not scale or not duration:
            raise ValueError('Invalid media timescale/duration')
        if duration/scale > movie_duration/movie_scale + 1/movie_scale:
            raise ValueError('Media duration lies outside movie')
        np,nz = child(data,dp,dz,b'minf')
        sp,sz = child(data,np,nz,b'stbl')
        if handler == b'vide':
            ep,ez = child(data,sp,sz,b'stsd')
            _header(data,ep,ez,8)
            entries = list(atoms(data,ep+8,ez))
            if not entries or len(entries) != _field(data,ep,ez,'>I',4)[0]:
                raise ValueError('Video has no sample descriptions')
            _check_video_samples(data,sp,sz,len(entries))
            video_ids.add(track_id)
        elif handler == b'mdta':
            if any(k == b'edts' for k,*_ in atoms(data,tp,tz)):
                raise ValueError('Metadata edits are unsupported')
            if abs(duration/scale-track_duration/movie_scale) > max(1/scale,1/movie_scale):
                raise ValueError('Metadata media/track durations do not match')
            metadata_tracks.append((tp,tz))
    if not video_ids:
        raise ValueError('Movie has no actual video track')
    for tp,tz in metadata_tracks:
        rp,rz = child(data,tp,tz,b'tref')
        cp,cz = child(data,rp,rz,b'cdsc')
        if cz-cp != 4 or _field(data,cp,cz,'>I')[0] not in video_ids:
            raise ValueError('Metadata must reference an existing video track')
    return movie_duration/movie_scale


def validate_pair(photo, video):
    """Read actual directories/sample tables/payloads, not a metadata-string search."""
    identifier = _photo_identifier(photo)
    data = Path(video).read_bytes()
    roots = list(atoms(data))
    if sum(k == b'moov' for k,*_ in roots) != 1 or any(k == b'moof' for k,*_ in roots):
        raise ValueError('Expected one nonfragmented movie')
    p, z = child(data, 0, len(data), b'moov')
    movie_seconds = _check_tracks(data, p, z)
    mp, mz = child(data, p, z, b'meta')
    # QuickTime meta is an atom container, unlike the ISO MP4 FullBox variant.
    # Read legacy exports for diagnostics, but never write that mixed encoding.
    legacy = data[mp:mp+4] == b'\0'*4
    content_start = mp+4 if legacy else mp
    kp, kz = child(data, content_start, mz, b'keys')
    _header(data, kp, kz, 8)
    keys = list(atoms(data, kp + 8, kz))
    if len(keys) != _field(data, kp, kz, '>I', 4)[0]:
        raise ValueError('Invalid movie key count')
    index = next((i + 1 for i, (k, _, q, r) in enumerate(keys)
                  if k == b'mdta' and data[q:r] == IDENTIFIER_KEY), None)
    if index is None:
        raise ValueError('Movie content identifier key is missing')
    ip, iz = child(data, content_start, mz, b'ilst')
    vp, vz = child(data, ip, iz, U32(index))
    dp, dz = child(data, vp, vz, b'data')
    if _field(data, dp, dz, '>II')[0] != 1:
        raise ValueError('Invalid movie identifier datatype')
    try:
        movie_identifier = data[dp + 8:dz].decode('ascii')
    except UnicodeError as exc:
        raise ValueError('Invalid movie identifier encoding') from exc
    if identifier != movie_identifier:
        raise ValueError('Photo/movie identifiers do not match')
    mdats = [(q, r) for k, _, q, r in atoms(data) if k == b'mdat']
    markers = []
    for k, _, tp, tz in atoms(data, p, z):
        if k != b'trak':
            continue
        dp, dz = child(data, tp, tz, b'mdia')
        hp, hz = child(data, dp, dz, b'hdlr')
        if data[hp + 8:hp + 12] != b'mdta':
            continue
        hp, hz = child(data, dp, dz, b'mdhd')
        scale, duration = _field(data, hp, hz, '>II', 12)
        np, nz = child(data, dp, dz, b'minf')
        sp, sz = child(data, np, nz, b'stbl')
        ep, ez = child(data, sp, sz, b'stsd')
        _header(data, ep, ez, 8)
        if _field(data, ep, ez, '>I', 4)[0] != 1:
            raise ValueError('Expected one metadata description')
        bp, bz = child(data, ep + 8, ez, b'mebx')
        if _field(data, bp, bz, '>H', 6)[0] != 1:
            raise ValueError('Invalid metadata data reference')
        kp, kz = child(data, bp + 8, bz, b'keys')
        local_ids = []
        for local, _, lp, lz in atoms(data, kp, kz):
            qp, qz = child(data, lp, lz, b'keyd')
            yp, yz = child(data, lp, lz, b'dtyp')
            if data[qp:qz] == b'mdta' + KEY and data[yp:yz] == U32(0, 65):
                local_ids.append(local)
        if len(local_ids) != 1 or local_ids[0] in (U32(0),U32(0xffffffff)):
            raise ValueError('Expected one still-image-time key declaration')
        cp, cz = child(data, sp, sz, b'co64')
        _header(data, cp, cz, 16)
        if cz-cp != 16 or _field(data, cp, cz, '>I', 4)[0] != 1:
            raise ValueError('Expected one metadata chunk')
        offset = _field(data, cp, cz, '>Q', 8)[0]
        cp, cz = child(data, sp, sz, b'stsc')
        _header(data, cp, cz, 20)
        if cz-cp != 20:
            raise ValueError('Invalid chunk table length')
        mappings = _field(data, cp, cz, '>IIII', 4)
        cp, cz = child(data, sp, sz, b'stsz')
        _header(data, cp, cz, 12)
        fixed, n = _field(data, cp, cz, '>II', 4)
        if not 1 <= n <= 10000 or cz-cp != (12 if fixed else 12+4*n):
            raise ValueError('Invalid metadata sample table length/count')
        if mappings != (1, 1, n, 1):
            raise ValueError('Invalid metadata chunk mapping')
        sizes = [fixed] * n if fixed else list(_field(data, cp, cz, '>' + 'I' * n, 12))
        cp, cz = child(data, sp, sz, b'stts')
        _header(data, cp, cz, 8)
        nentries = _field(data, cp, cz, '>I', 4)[0]
        if not 1 <= nentries <= n or cz-cp != 8+8*nentries:
            raise ValueError('Invalid metadata timing table length')
        deltas = []
        for i in range(nentries):
            count, delta = _field(data, cp, cz, '>II', 8+8*i)
            if not count or not delta or len(deltas)+count > n:
                raise ValueError('Invalid metadata timing entry')
            deltas.extend([delta] * count)
        if len(deltas) != n or sum(deltas) != duration:
            raise ValueError('Invalid metadata timing table')
        elapsed = 0
        for size, delta in zip(sizes, deltas):
            if size < 8 or not any(q <= offset and offset + size <= r for q, r in mdats):
                raise ValueError('Metadata sample does not reference an mdat payload')
            for local, _, qp, qz in atoms(data, offset, offset + size):
                if local in local_ids:
                    if data[qp:qz] not in (b'\x00', b'\xff'):
                        raise ValueError('Invalid still-image-time payload')
                    if not 0 <= elapsed/scale < movie_seconds or (elapsed+delta)/scale > movie_seconds+1e-5:
                        raise ValueError('Marker lies outside movie')
                    markers.append({'time': elapsed / scale, 'duration': delta / scale,
                                    'offset': offset, 'sample_size': size})
            offset += size
            elapsed += delta
    if len(markers) != 1:
        raise ValueError('Expected one real still-image-time metadata sample')
    return {'valid': True, 'identifier': identifier, 'still_image_time': markers[0]['time'],
            'metadata_sample': markers[0], 'movie_metadata_encoding': 'legacy-iso-fullbox' if legacy else 'quicktime', 'device_acceptance': 'unverified'}


def export_live_photo(source, output_stem, settings, cancel=None, progress=None):
    from . import media
    source, stem = Path(source), Path(output_stem)
    photo, video, archive = (Path(str(stem) + suffix) for suffix in ('.jpg', '.mov', '.zip'))
    if any(path.resolve() == source.resolve() for path in (photo, video, archive)):
        raise ValueError('Export must not overwrite the source')
    if cancel is not None and cancel.is_set():
        raise RuntimeError('Export cancelled')
    stem.parent.mkdir(parents=True, exist_ok=True)
    info = media.probe(source, cancel=cancel)
    left, right = clip_window(info['duration'], settings.start, settings.end, settings.cover)
    identifier = str(uuid.uuid4()).upper()
    clip_settings = replace(settings, start=left, end=right)
    media.export_video(source, video, clip_settings, cancel, progress)
    # Select the cover from the final transformed clip, not a separately scaled
    # source frame: this guarantees the JPEG matches the actual CFR movie frame.
    timestamps = media.frame_timestamps(video, cancel=cancel)
    index = min(range(len(timestamps)), key=lambda i: abs(timestamps[i] - (settings.cover - left)))
    still_settings = replace(settings, crop=None, fit='stretch', start=0, end=None)
    media.extract_frame(video, photo, index, still_settings, cancel)
    actual_cover = timestamps[index]
    write_photo(photo, identifier)
    write_motion_metadata(video, identifier, actual_cover, settings.fps)
    validation = validate_pair(photo, video)
    if cancel is not None and cancel.is_set():
        raise RuntimeError('Export cancelled')
    manifest = {'identifier': identifier, 'photo': photo.name, 'video': video.name,
                'source_interval': [left, right], 'cover_source_seconds': settings.cover,
                'validation': validation,
                'notice': 'Structural pair validation only. Apple Photos import and iPhone wallpaper acceptance are unverified.'}
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(photo, photo.name)
        bundle.write(video, video.name)
        bundle.writestr('manifest.json', json.dumps(manifest, indent=2, ensure_ascii=False))
    if progress:
        progress(100, 'Live Photo 文件对与元数据结构已验证；设备识别待验证')
    return {'photo': photo, 'video': video, 'zip': archive, 'identifier': identifier,
            'validation': validation}

