import unittest
from pathlib import Path
import tempfile
import struct

class LivePhotoTests(unittest.TestCase):
    def test_makernote_is_real_exif_directory(self):
        from wallpaper_studio.livephoto import apple_makernote
        m = apple_makernote('12345678-1234-1234-1234-123456789ABC')
        self.assertEqual(m[:14], b'Apple iOS\0\0\x01MM')
        self.assertEqual(struct.unpack('>H', m[14:16])[0], 1)
        tag, typ, count, offset = struct.unpack('>HHII', m[16:28])
        self.assertEqual((tag, typ, count), (17, 2, 37))
        self.assertEqual(m[offset:offset+count], b'12345678-1234-1234-1234-123456789ABC\0')

    def test_clip_window_rejects_short_and_centers(self):
        from wallpaper_studio.livephoto import clip_window
        self.assertEqual(clip_window(10, 0, None, 5), (3.5, 6.5))
        self.assertEqual(clip_window(10, 0, None, 0), (0, 3))
        with self.assertRaises(ValueError):
            clip_window(2, 0, None, 1)
        with self.assertRaises(ValueError):
            clip_window(10, 0, 3, 5)


class LivePhotoIntegrationTests(unittest.TestCase):
    def test_pair_has_true_metadata_sample_and_survives_decode(self):
        import subprocess, hashlib, zipfile, json
        from PIL import Image
        from wallpaper_studio.media import ffmpeg_path
        from wallpaper_studio.models import EditSettings
        from wallpaper_studio.livephoto import export_live_photo, validate_pair
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / 'source.mp4'
            subprocess.run([str(ffmpeg_path()), '-y', '-f', 'lavfi', '-i',
                            'testsrc2=size=160x120:rate=10:duration=5', '-c:v', 'libx264',
                            '-pix_fmt', 'yuv420p', str(source)], check=True, capture_output=True)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            result = export_live_photo(source, folder / 'pair', EditSettings(width=120, height=80, cover=2.5, fps=10))
            self.assertEqual(digest, hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(Image.open(result['photo']).size, (120, 80))
            report = validate_pair(result['photo'], result['video'])
            self.assertAlmostEqual(report['still_image_time'], 1.5, places=4)
            payload = result['video'].read_bytes()
            offset = report['metadata_sample']['offset']
            self.assertEqual(payload[offset:offset+9], struct.pack('>II', 9, 1) + b'\x00')
            decoded = subprocess.run([str(ffmpeg_path()), '-v', 'error', '-i', str(result['video']),
                                      '-map', '0:v:0', '-f', 'null', '-'], capture_output=True)
            self.assertEqual(decoded.returncode, 0, decoded.stderr)
            metadata = subprocess.run([str(ffmpeg_path()), '-hide_banner', '-i', str(result['video'])], capture_output=True)
            self.assertIn(b'Data: none (mebx', metadata.stderr)
            with zipfile.ZipFile(result['zip']) as archive:
                manifest = json.loads(archive.read('manifest.json'))
                self.assertEqual(manifest['validation']['device_acceptance'], 'unverified')
            # Wrong UUID must fail even though metadata sample is otherwise valid.
            mismatch = payload.replace(result['identifier'].encode('ascii'),
                                       b'FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF')
            result['video'].write_bytes(mismatch)
            with self.assertRaisesRegex(ValueError, 'identifiers do not match'):
                validate_pair(result['photo'], result['video'])
            # Replace only metadata trak with free: movie-level labels remain,
            # but a label-only file is not a Live Photo pair.
            from wallpaper_studio.livephoto import atoms, child
            moovp, moovz = child(payload, 0, len(payload), b'moov')
            no_track = bytearray(payload)
            metadata_tracks = [a for k, a, q, r in atoms(payload, moovp, moovz)
                               if k == b'trak' and b'mebx' in payload[q:r]]
            self.assertEqual(len(metadata_tracks), 1)
            no_track[metadata_tracks[0]+4:metadata_tracks[0]+8] = b'free'
            result['video'].write_bytes(no_track)
            with self.assertRaisesRegex(ValueError, 'real still-image-time'):
                validate_pair(result['photo'], result['video'])
            result['video'].write_bytes(payload)
            # Tampering with actual sample payload must invalidate; strings remain intact.
            damaged = bytearray(payload)
            damaged[offset+8] = 2
            result['video'].write_bytes(damaged)
            with self.assertRaises(ValueError):
                validate_pair(result['photo'], result['video'])

    def test_photo_writer_round_trips_real_makernote(self):
        from PIL import Image
        from wallpaper_studio.livephoto import write_photo, _photo_identifier
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'photo.jpg'
            Image.new('RGB', (16, 16), 'red').save(path)
            identifier = '12345678-1234-1234-1234-123456789ABC'
            write_photo(path, identifier)
            self.assertEqual(_photo_identifier(path), identifier)

class MetadataBinaryTests(unittest.TestCase):
    def test_insertion_preserves_video_chunk_bytes_and_key_declarations(self):
        from wallpaper_studio.livephoto import atom, full, U32, write_motion_metadata, atoms, child
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'tiny.mov'
            mvhd = full('mvhd', U32(0, 0, 1000, 3000) + b'\0' * 80)
            tkhd = full('tkhd', U32(0, 0, 1, 0, 3000) + b'\0' * 60)
            hdlr = full('hdlr', U32(0) + b'vide' + b'\0' * 12)
            old_moov = atom('moov', mvhd + atom('trak', tkhd + atom('mdia', hdlr)))
            p.write_bytes(atom('ftyp', b'qt  '+U32(0)) + old_moov + atom('mdat', b'video-chunk-sentinel'))
            before = p.read_bytes()
            payload_offset = before.index(b'video-chunk-sentinel')
            write_motion_metadata(p, '12345678-1234-1234-1234-123456789ABC', 1.5, 30)
            result = p.read_bytes()
            self.assertEqual(result[payload_offset:payload_offset+20], b'video-chunk-sentinel')
            roots = list(atoms(result))
            self.assertEqual([a[0] for a in roots], [b'ftyp', b'free', b'mdat', b'mdat', b'moov'])
            mp, mz = child(result, roots[-1][2], roots[-1][3], b'mvhd')
            self.assertEqual(struct.unpack_from('>I', result, mz-4)[0], 3)
            # Direct independent byte grammar: keys->local(1)->keyd + dtyp.
            key = b'com.apple.quicktime.still-image-time'
            expected = atom('keys', atom(U32(1), atom('keyd', b'mdta'+key)+atom('dtyp', U32(0,65))))
            self.assertIn(expected, result)
            self.assertEqual(result[roots[-2][2]:roots[-2][3]],
                             atom(U32(0)) + atom(U32(1), b'\x00') + atom(U32(0)))




class StrictValidationTests(unittest.TestCase):
    def test_corrupt_track_relationships_and_headers_rejected(self):
        import subprocess
        from wallpaper_studio.media import ffmpeg_path
        from wallpaper_studio.models import EditSettings
        from wallpaper_studio.livephoto import export_live_photo, validate_pair, child, atoms
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / 'source.mp4'
            subprocess.run([str(ffmpeg_path()), '-y', '-f', 'lavfi', '-i',
                            'testsrc2=size=32x24:rate=10:duration=3', '-c:v', 'libx264',
                            '-pix_fmt', 'yuv420p', str(source)], check=True, capture_output=True)
            pair = export_live_photo(source, folder / 'pair', EditSettings(width=32,height=24,fps=10))
            original = pair['video'].read_bytes()
            mp,mz = child(original,0,len(original),b'moov')
            tracks=[(p,z) for k,a,p,z in atoms(original,mp,mz) if k==b'trak']
            metadata=next((p,z) for p,z in tracks if b'mebx' in original[p:z])
            video=next((p,z) for p,z in tracks if b'mebx' not in original[p:z])
            vp,vz=child(original,*video,b'tkhd')
            hp,hz=child(original,*metadata,b'tkhd')
            mutations=[]
            damaged=bytearray(original)
            rp,rz=child(original,*metadata,b'tref')
            cp,cz=child(original,rp,rz,b'cdsc')
            struct.pack_into('>I',damaged,cp,999)
            mutations.append(('nonexistent reference',damaged))
            damaged=bytearray(original)
            damaged[hp+12:hp+16]=original[vp+12:vp+16]
            mutations.append(('duplicate track ID',damaged))
            damaged=bytearray(original)
            # hdlr shorter than its mandatory handler type, nested atom remains parseable.
            dp,dz=child(original,*metadata,b'mdia')
            fp,fz=child(original,dp,dz,b'hdlr')
            struct.pack_into('>I',damaged,fp-8,16)
            damaged[fp+8:fz]=b'\0'*(fz-fp-8)
            mutations.append(('short handler',damaged))
            damaged=bytearray(original)
            fp,fz=child(original,mp,mz,b'mvhd')
            struct.pack_into('>I',damaged,fp+16,1)
            mutations.append(('marker outside movie',damaged))
            damaged=bytearray(original)
            fp,fz=child(original,dp,dz,b'mdhd')
            struct.pack_into('>I',damaged,fp+12,0)
            mutations.append(('zero metadata scale',damaged))
            damaged=bytearray(original)
            np,nz=child(original,dp,dz,b'minf')
            sp,sz=child(original,np,nz,b'stbl')
            fp,fz=child(original,sp,sz,b'stsz')
            struct.pack_into('>I',damaged,fp-8,8)
            mutations.append(('short sample table',damaged))
            damaged=bytearray(original)
            fp,fz=child(original,sp,sz,b'stts')
            struct.pack_into('>I',damaged,fp+8,0xffffffff)
            mutations.append(('oversized timing entry',damaged))
            damaged=bytearray(original)
            vdp,vdz=child(original,*video,b'mdia')
            vnp,vnz=child(original,vdp,vdz,b'minf')
            vsp,vsz=child(original,vnp,vnz,b'stbl')
            vcp,vcz=child(original,vsp,vsz,b'stsz')
            struct.pack_into('>I',damaged,vcp+8,0)
            mutations.append(('video has no actual samples',damaged))
            damaged=bytearray(original)
            vcp,vcz=child(original,vsp,vsz,b'stco')
            struct.pack_into('>I',damaged,vcp+8,0)
            mutations.append(('video chunk points outside mdat',damaged))
            for name,damaged in mutations:
                pair['video'].write_bytes(damaged)
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        validate_pair(pair['photo'],pair['video'])
            pair['video'].write_bytes(original[:-3])
            with self.assertRaises(ValueError):
                validate_pair(pair['photo'],pair['video'])

if __name__ == '__main__':
    unittest.main()

def test_quicktime_meta_is_not_iso_fullbox():
    from wallpaper_studio.livephoto import _movie_metadata,atoms
    payload=_movie_metadata('12345678-1234-1234-1234-123456789ABC')
    assert list(atoms(payload,8))[0][0]==b'hdlr'

def test_jpeg_makernote_uses_undefined_exif_type(tmp_path):
    import struct
    from PIL import Image
    from wallpaper_studio.livephoto import write_photo
    p=tmp_path/'photo.jpg';Image.new('RGB',(16,16)).save(p)
    write_photo(p,'12345678-1234-1234-1234-123456789ABC')
    exif=Image.open(p).info['exif'][6:]
    endian='<' if exif[:2]==b'II' else '>'
    def entries(offset):
        n=struct.unpack_from(endian+'H',exif,offset)[0]
        return [struct.unpack_from(endian+'HHII',exif,offset+2+i*12) for i in range(n)]
    offset=struct.unpack_from(endian+'I',exif,4)[0]
    pointer=next(value for tag,typ,n,value in entries(offset) if tag==34665)
    types={tag:typ for tag,typ,n,value in entries(pointer)}
    assert types[37500]==7
    assert types[37121]==7
    assert {36864,37121,40961,40962,40963}.issubset(types)
