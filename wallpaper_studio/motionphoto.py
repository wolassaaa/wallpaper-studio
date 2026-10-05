"""Experimental Honor motion-JPEG wrapper derived from one user reference.
The opaque vendor header is a reference profile, not a published format schema.
No original EXIF, camera identifiers, photo pixels or video are bundled.
Recognition in Honor Gallery / WeChat / Apple Photos requires device testing.
"""
import io,re,struct
from PIL import Image
HONOR_HEADER=bytes.fromhex('020100000101010001016400850200005a0b0000850200000000321e110100000c010000000000000000040000000000000100000000000000000000000000000000000000000000000000000000000000000000c805ff3f00000000000000000000000000000000000000000000000000000000000000000000000000000000800000001c1508004869486f6e6f725f45686472456e00000000000000010000004869486f6e6f725f457874496e666f0000000000')


def _check_movie(movie):
    if len(movie)<16 or movie[4:8]!=b'ftyp':raise ValueError('Expected MP4 ftyp')
    p=0
    while p<len(movie):
        if p+8>len(movie):raise ValueError('Truncated movie box')
        size=int.from_bytes(movie[p:p+4],'big');minimum=8
        if size==1:
            if p+16>len(movie):raise ValueError('Truncated extended movie box')
            size=int.from_bytes(movie[p+8:p+16],'big');minimum=16
        elif size==0:size=len(movie)-p
        if size<minimum or p+size>len(movie):raise ValueError('Invalid movie box size')
        p+=size


def _check_photo(photo):
    if not photo.startswith(b'\xff\xd8') or not photo.endswith(b'\xff\xd9'):
        raise ValueError('Expected standalone JPEG without appended data')
    with Image.open(io.BytesIO(photo)) as image:
        if image.format!='JPEG':raise ValueError('Expected JPEG')
        image.verify()


def build_honor(photo,movie,cover_ms=500,header=HONOR_HEADER):
    photo,movie=bytes(photo),bytes(movie)
    _check_photo(photo);_check_movie(movie)
    if type(cover_ms) is not int or not 0<=cover_ms<=99999999:raise ValueError('Invalid presentation timestamp')
    if header!=HONOR_HEADER:raise ValueError('Unknown vendor header profile')
    def field(value):
        value=value.encode('ascii')
        if len(value)>20:raise ValueError('Trailer field exceeds 20 bytes')
        return value.ljust(20,b' ')
    footer=field('v2_f11')+field('0:'+str(cover_ms))+field('LIVE_'+str(len(movie)+20))
    return photo+header+movie+footer


def split_honor(body):
    body=bytes(body)
    if len(body)<60+len(HONOR_HEADER):raise ValueError('Missing Honor footer')
    footer=body[-60:]
    if footer[:20].strip()!=b'v2_f11':raise ValueError('Unknown Honor trailer profile')
    clock=re.fullmatch(rb'0:(\d+)',footer[20:40].strip())
    size=re.fullmatch(rb'LIVE_(\d+)',footer[40:].strip())
    if clock is None or size is None:raise ValueError('Malformed Honor footer')
    length=int(size.group(1))-20
    start=len(body)-60-length;header_start=start-len(HONOR_HEADER)
    if length<16 or header_start<0 or body[header_start:start]!=HONOR_HEADER:raise ValueError('Vendor header/length mismatch')
    photo=body[:header_start];movie=body[start:-60]
    _check_photo(photo);_check_movie(movie)
    return {'photo':photo,'movie':movie,'header':body[header_start:start],
            'cover_ms':int(clock.group(1)),'movie_offset':start,'video_bytes':length,
            'profile':'experimental-honor-v2_f11','device_acceptance':'unverified'}


def export_honor_video(video,work,cover_time,cancel=None):
    """Generate a fresh cover from final 30fps MP4 and wrap one experimental JPG."""
    from pathlib import Path
    from .media import ffmpeg_path
    from .source import run_tool,check_cancel
    import json
    work=Path(work);movie=work/'android-motion.mp4';photo=work/'android-cover.jpg';output=work/'wallpaper-motion.jpg'
    ff=str(ffmpeg_path())
    run_tool([ff,'-y','-v','error','-i',str(video),'-map','0:v:0','-map','0:a:0','-map_metadata','-1','-vf','fps=30','-c:v','libx265','-preset','fast','-crf','20','-tag:v','hvc1','-x265-params','pools=4:frame-threads=2:log-level=error','-c:a','aac','-brand','mp42',str(movie)],cancel=cancel,timeout=300)
    probe=json.loads(run_tool([str(ffmpeg_path().with_name('ffprobe.exe')),'-v','error','-show_streams','-of','json',str(movie)],cancel=cancel,timeout=60))
    stream=next(v for v in probe['streams'] if v['codec_type']=='video')
    count=int(stream['nb_frames']);frame=min(count-1,max(0,round(cover_time*30)))
    run_tool([ff,'-y','-v','error','-i',str(movie),'-vf',f'select=eq(n\\,{frame})','-frames:v','1','-q:v','2',str(photo)],cancel=cancel,timeout=60)
    with Image.open(photo) as im:im.convert('RGB').save(photo,format='JPEG',quality=95)
    body=build_honor(photo.read_bytes(),movie.read_bytes(),round(frame/30*1000))
    check_cancel(cancel)
    with output.open('xb') as handle:handle.write(body)
    parsed=split_honor(output.read_bytes())
    if parsed['movie']!=movie.read_bytes() or parsed['photo']!=photo.read_bytes():raise ValueError('Honor roundtrip mismatch')
    run_tool([ff,'-v','error','-i',str(movie),'-f','null','-'],cancel=cancel,timeout=180)
    return {'photo':photo,'video':movie,'file':output,'validation':{'valid':True,'profile':parsed['profile'],'cover_ms':parsed['cover_ms'],'video_bytes':parsed['video_bytes'],'device_acceptance':'unverified'}}
