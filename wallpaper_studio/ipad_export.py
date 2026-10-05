"""iPad measured composition and experimental single-file motion packing.
No private wallpaper media is bundled. Repeated metadata profile is experimental;
Windows structure verification is not Apple Photos/device acceptance.
"""
from pathlib import Path
import json,struct,uuid,zipfile,threading,sys
from .livephoto import atom,full,atoms,child,U32,MATRIX,IDENTIFIER_KEY,write_photo,_photo_identifier,_movie_metadata
MOTION_SEED = [('00000000000000010000021b6d65627800000000000000010000020b6b65797300000203000000010000002f6b6579646d647461636f6d2e6170706c652e717569636b74696d652e6c6976652d70686f746f2d696e666f000000436474797000000001636f6d2e6170706c652e717569636b74696d652e636f6d2e6170706c652e717569636b74696d652e6c6976652d70686f746f2d696e666f0000017173657475000001596366677662706c6973743030d301020304050c5f10214c69766550686f746f4d6574616461746153657475704461746156657273696f6e5d53797374656d56657273696f6e5f10114672616d65776f726b56657273696f6e731001d3060708090a0b5f101350726f647563744275696c6456657273696f6e5b50726f647563744e616d655e50726f6475637456657273696f6e583231413532373768596950686f6e65204f535431372e30d40d0e0f10111213145a436f72654d6f74696f6e5d434d43617074757265436f72655e483130495350536572766963657359436f72654d6564696158323836382e302e32573434362e352e335432302e325e333034352e36392e322e31312e340008000f0033004100550057005e00740080008f009800a200a700b000bb00c900d800e200eb00f300f800000000000002010000000000000015000000000000000000000000000001070000001064696d7300000780000005a0000000186374707300000010647479700000000000000000', '000000900000000103000000bdc36d3ce3b5eb6d800000007b80ad425a2d64410a08cb3e7feea6bd79e9f63f000080400400ff00000000000000000000000000000000000000000007000000525e873ee66e52bf1b2a6ac4d37862bf761ed23dde3f8ec313f52f39b2f04439ff309dbf1a17f1ed1b070000206796ed1b07000000000000000000000000000000000000', 57), ('0000000000000001000000b86d6562780000000000000001000000a86b6579730000004800000001000000306b6579646d647461636f6d2e6170706c652e717569636b74696d652e7374696c6c2d696d6167652d74696d65000000106474797000000000000000410000005800000002000000406b6579646d647461636f6d2e6170706c652e717569636b74696d652e6c6976652d70686f746f2d7374696c6c2d696d6167652d7472616e73666f726d00000010647479700000000000000053', '0000000900000001ff00000050000000023ff00000000000000000000000000000000000000000000000000000000000003ff00000000000000000000000000000000000000000000000000000000000003ff0000000000000', 1)]

def _heic_prefix_end(data):
    data = bytes(data)
    if len(data) < 20 or data[4:8] != b'ftyp':
        raise ValueError('Expected HEIC container')
    first = int.from_bytes(data[:4], 'big')
    if first < 16 or first > len(data) or b'heic' not in data[8:first]:
        raise ValueError('Expected HEIC brand')
    position = 0
    while position < len(data):
        if data[position+4:position+16] == b'uuid' + bytes(8):
            return position
        if position+8 > len(data): raise ValueError('Truncated HEIC box')
        size = int.from_bytes(data[position:position+4], 'big')
        header = 8
        if size == 1:
            if position+16 > len(data): raise ValueError('Truncated HEIC extended box')
            size = int.from_bytes(data[position+8:position+16], 'big'); header = 16
        if size < header or position+size > len(data): raise ValueError('Invalid HEIC box')
        position += size
    return position


def build_hybrid(still, movie):
    """Empirical user-sample envelope, not a claim of Apple-standard HEIF."""
    still, movie = bytes(still), bytes(movie)
    if _heic_prefix_end(still) != len(still): raise ValueError('Already contains a movie')
    if len(movie) < 16 or movie[4:8] != b'ftyp': raise ValueError('Missing movie ftyp')
    if len(movie)+4 > 0xffffffff: raise ValueError('Envelope exceeds 32-bit size')
    return still + struct.pack('<I', len(movie)+4) + b'uuid' + bytes(8) + movie


def split_hybrid(data):
    data = bytes(data); boundary = _heic_prefix_end(data)
    if boundary == len(data) or boundary+16 > len(data): raise ValueError('Missing envelope')
    length = int.from_bytes(data[boundary:boundary+4], 'little')
    movie = data[boundary+16:]
    if length != len(movie)+4 or len(movie)<16 or movie[4:8] != b'ftyp':
        raise ValueError('Envelope length/movie signature mismatch')
    return data[:boundary], movie


def crop_window(source_size, screen_size, zoom=1.0, center=(.5,.5)):
    """Parameterized aspect-fill MODEL; not Apple's undisclosed crop algorithm."""
    import math
    iw,ih=source_size; sw,sh=screen_size; cx,cy=center
    values=[iw,ih,sw,sh,zoom,cx,cy]
    if not all(math.isfinite(v) for v in values) or min(iw,ih,sw,sh)<=0 or zoom<1 or not 0<=cx<=1 or not 0<=cy<=1:
        raise ValueError('Invalid crop parameters')
    scale=max(sw/iw,sh/ih)*zoom; w,h=sw/scale,sh/scale
    return max(0,min(iw-w,cx*iw-w/2)),max(0,min(ih-h,cy*ih-h/2)),w,h


def fit_crop(points, screen_size, source_size):
    """Fit axis-aligned source->screenshot transform from observed fiducials."""
    import numpy as np
    if len(points)<3: raise ValueError('At least three non-collinear fiducials required')
    a=np.asarray(points,dtype=float)
    if a.shape[1:]!=(4,) or not np.isfinite(a).all(): raise ValueError('Invalid fiducials')
    if np.linalg.matrix_rank(np.column_stack((a[:,:2],np.ones(len(a)))))<3:
        raise ValueError('Fiducials must be non-collinear')
    sw,sh=screen_size; iw,ih=source_size
    if not np.isfinite([sw,sh,iw,ih]).all() or min(sw,sh,iw,ih)<=0: raise ValueError('Invalid dimensions')
    sx,tx=np.linalg.lstsq(np.column_stack((a[:,0],np.ones(len(a)))),a[:,2],rcond=None)[0]
    sy,ty=np.linalg.lstsq(np.column_stack((a[:,1],np.ones(len(a)))),a[:,3],rcond=None)[0]
    if min(sx,sy)<=0: raise ValueError('Degenerate or rotated mapping')
    predicted=np.column_stack((a[:,0]*sx+tx,a[:,1]*sy+ty))
    residual=float(np.sqrt(np.mean((predicted-a[:,2:])**2)))
    rect=[float(-tx/sx),float(-ty/sy),float(sw/sx),float(sh/sy)]
    return {'scale_xy':[float(sx),float(sy)],'offset_xy':[float(tx),float(ty)],
            'visible_rect':rect,'center_normalized':[(rect[0]+rect[2]/2)/iw,(rect[1]+rect[3]/2)/ih],
            'nonuniform_scale':bool(abs(sx-sy)/max(sx,sy)>.01),'residual_pixels':residual,
            'extends_beyond_source':rect[0]<-1 or rect[1]<-1 or rect[0]+rect[2]>iw+1 or rect[1]+rect[3]>ih+1,
            'meaning':'Measured screenshot fit, not system-algorithm identification'}


def _valid_movie_end(data):
    end=0
    while end+8<=len(data):
        size=int.from_bytes(data[end:end+4],'big'); header=8
        if size==1:
            if end+16>len(data):break
            size=int.from_bytes(data[end+8:end+16],'big');header=16
        if size<header or end+size>len(data):break
        end+=size
    return end


def _sample_tracks(data):
    p,z=child(data,0,_valid_movie_end(data),b'moov'); result=[]
    for k,_,tp,tz in atoms(data,p,z):
        if k!=b'trak':continue
        dp,dz=child(data,tp,tz,b'mdia');hp,hz=child(data,dp,dz,b'hdlr')
        if data[hp+8:hp+12] not in (b'mdta',b'meta'):continue
        mp,mz=child(data,dp,dz,b'minf');sp,sz=child(data,mp,mz,b'stbl')
        ep,ez=child(data,sp,sz,b'stsd');description=data[ep:ez]
        cp,cz=child(data,sp,sz,b'stsz');fixed,n=struct.unpack_from('>II',data,cp+4)
        sizes=[fixed]*n if fixed else list(struct.unpack_from('>'+'I'*n,data,cp+12))
        try:op,oz=child(data,sp,sz,b'stco');fmt='I'
        except ValueError:op,oz=child(data,sp,sz,b'co64');fmt='Q'
        offsets=struct.unpack_from('>'+fmt*int.from_bytes(data[op+4:op+8],'big'),data,op+8)
        cp,cz=child(data,sp,sz,b'stsc');count=int.from_bytes(data[cp+4:cp+8],'big')
        maps=[struct.unpack_from('>III',data,cp+8+12*i) for i in range(count)]
        samples=[];i=index=0
        for chunk,offset in enumerate(offsets,1):
            while index+1<len(maps) and chunk>=maps[index+1][0]:index+=1
            for _ in range(maps[index][1]):
                if i>=len(sizes) or offset+sizes[i]>len(data):raise ValueError('Invalid template samples')
                samples.append(data[offset:offset+sizes[i]]);offset+=sizes[i];i+=1
        if i!=n:raise ValueError('Incomplete template samples')
        result.append((description,samples))
    return result


def _lab_track(track_id,video_id,movie_scale,delay,scale,delta,samples,description,offset):
    media_duration=delta*len(samples); track_duration=round((delay+media_duration/scale)*movie_scale)
    tkhd=full('tkhd',U32(0,0,track_id,0,track_duration)+bytes(16)+MATRIX+U32(0,0),flags=3)
    mdhd=full('mdhd',U32(0,0,scale,media_duration)+struct.pack('>HH',0x55c4,0))
    hdlr=full('hdlr',b'mhlrmetaappl'+U32(1,0)+b'\x13Core Media Metadata')
    stsd=atom('stsd',description);stts=full('stts',U32(1,len(samples),delta))
    stsc=full('stsc',U32(1,1,len(samples),1))
    stsz=full('stsz',U32(0,len(samples))+b''.join(U32(len(s)) for s in samples))
    co64=full('co64',U32(1)+struct.pack('>Q',offset))
    stbl=atom('stbl',stsd+stts+stsc+stsz+co64)
    dinf=atom('dinf',full('dref',U32(1)+full('url ',flags=1)))
    gmhd=atom('gmhd',full('gmin',struct.pack('>HHHHHH',64,32768,32768,32768,0,0)))
    edits=[]
    if delay:edits.append(struct.pack('>IiHH',round(delay*movie_scale),-1,1,0))
    edits.append(struct.pack('>IiHH',round(media_duration/scale*movie_scale),0,1,0))
    edts=atom('edts',full('elst',U32(len(edits))+b''.join(edits)))
    return atom('trak',tkhd+edts+atom('tref',atom('cdsc',U32(video_id)))+atom('mdia',mdhd+hdlr+atom('minf',gmhd+dinf+stbl)))


def template_motion(path,template,identifier,width,height,cover_time=.5):
    """Experimental 1s/60fps template profile, not general camera-motion synthesis."""
    data=Path(path).read_bytes();tracks=[(bytes.fromhex(d),[bytes.fromhex(p)]*n) for d,p,n in MOTION_SEED]
    info=[(desc,s) for desc,s in tracks if b'live-photo-info' in desc]
    marker=[(desc,s) for desc,s in tracks if b'still-image-time' in desc]
    if len(info)!=1 or len(marker)!=1 or len(info[0][1])!=57 or len(set(info[0][1]))!=1:
        raise ValueError('Expected repeated-payload 57-sample user reference profile')
    desc,samples=info[0];desc=bytearray(desc)
    # Setup declares reference dimensions; change these for the square test.
    index=desc.find(b'dims')
    if index<0 or int.from_bytes(desc[index-4:index],'big')!=16:raise ValueError('Missing dimensions setup')
    struct.pack_into('>II',desc,index+4,width,height)
    _,a,p,z=next(t for t in atoms(data) if t[0]==b'moov')
    mp,mz=child(data,p,z,b'mvhd');movie_scale,duration=struct.unpack_from('>II',data,mp+12)
    ids=[];video_id=None
    for kind,_,tp,tz in atoms(data,p,z):
        if kind!=b'trak':continue
        hp,hz=child(data,tp,tz,b'tkhd');tid=int.from_bytes(data[hp+12:hp+16],'big');ids.append(tid)
        dp,dz=child(data,tp,tz,b'mdia');hp,hz=child(data,dp,dz,b'hdlr')
        if data[hp+8:hp+12]==b'vide':video_id=tid
        if data[hp+8:hp+12] in (b'mdta',b'meta'):raise ValueError('Input already contains metadata tracks')
    if video_id is None:raise ValueError('Missing video track')
    if not .999<=duration/movie_scale<=1.06:raise ValueError('Template experiment requires a one-second clip')
    first=max(ids)+1;payload=b''.join(samples)+b''.join(marker[0][1]);offset=len(data)+8
    info_track=_lab_track(first,video_id,movie_scale,.05,60000,1000,samples,bytes(desc),offset)
    marker_track=_lab_track(first+1,video_id,movie_scale,cover_time,600,1,marker[0][1],marker[0][0],offset+sum(map(len,samples)))
    content=bytearray(data[p:z]);struct.pack_into('>I',content,mz-p-4,first+2)
    original=bytearray(data);original[a+4:a+8]=b'free'
    Path(path).write_bytes(original+atom('mdat',payload)+atom('moov',content+_movie_metadata(identifier)+info_track+marker_track))


def movie_identifier(data):
    p,z=child(data,0,_valid_movie_end(data),b'moov')
    for kind,_,mp,mz in atoms(data,p,z):
        if kind!=b'meta':continue
        base=mp+4 if data[mp:mp+4]==bytes(4) else mp
        try:kp,kz=child(data,base,mz,b'keys');ip,iz=child(data,base,mz,b'ilst')
        except ValueError:continue
        keys=list(atoms(data,kp+8,kz));wanted=[i+1 for i,(k,a,q,r) in enumerate(keys) if data[q:r]==IDENTIFIER_KEY]
        for k,a,q,r in atoms(data,ip,iz):
            if int.from_bytes(k,'big') in wanted:
                vp,vz=child(data,q,r,b'data');return data[vp+8:vz].decode('ascii')
    raise ValueError('Missing movie identifier')


def pack_files(photo,movie,output):
    photo,movie,output=map(Path,(photo,movie,output))
    if output.resolve() in (photo.resolve(),movie.resolve()):raise ValueError('Output overlaps input')
    if output.exists():raise FileExistsError(output)
    _register_heif()
    identifier=_photo_identifier(photo)
    still,motion=photo.read_bytes(),movie.read_bytes()
    if movie_identifier(motion)!=identifier:raise ValueError('Pair identifiers do not match')
    body=build_hybrid(still,motion);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as handle:handle.write(body)
    if split_hybrid(output.read_bytes())!=(still,motion):raise ValueError('Roundtrip verification failed')
    return {'format':'sample-hybrid-heic','identifier':identifier,'bytes':len(body),'device_acceptance':'unverified'}


def pack_livp(photo,movie,output):
    photo,movie,output=map(Path,(photo,movie,output))
    if output.exists():raise FileExistsError(output)
    _register_heif();identifier=_photo_identifier(photo)
    if movie_identifier(movie.read_bytes())!=identifier:raise ValueError('Pair identifiers do not match')
    stem='IMB_'+identifier[:8]+'.HEIC'
    with zipfile.ZipFile(output,'x',zipfile.ZIP_STORED) as archive:
        archive.write(photo,stem+'.heic');archive.write(movie,stem+'.mov')
    # Compatible ZIP-comment profile observed in Hiwoniu/live-photos (MIT).
    data=output.read_bytes();values=[]
    with zipfile.ZipFile(output) as archive:
        for entry in archive.infolist():
            header=entry.header_offset;name,extra=struct.unpack_from('<HH',data,header+26)
            values.extend((header+30+name+extra,entry.compress_size))
    comment=bytes.fromhex('0002')+struct.pack('>II',*values[:2])+bytes.fromhex('0003')+struct.pack('>II',*values[2:])+b'1000LIVP'
    with zipfile.ZipFile(output,'a') as archive:archive.comment=comment
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
    return {'format':'experimental-livp','identifier':identifier,'device_acceptance':'unverified'}


def _register_heif():
    import pillow_heif
    pillow_heif.register_heif_opener(thumbnails=False)


IPAD_PROFILE = {
    'id':'ipad-m4-11-user-grid-ipados-27.2-v1',
    'device':'iPad Pro 11 M4 target', 'os_version_user_reported':'27.2',
    'reference_canvas':[2420,2420],
    'shared_rect':[239.56180276172037,90.6291510304171,1578.532221689846,1667.5580574511262],
    'landscape_rect':[0,90.6291510304171,2420,1667.5580574511262],
    'portrait_rect':[239.56180276172037,71.69735853009095,1578.532221689846,2292.938277712863],
    'calibration_scope':'Two static grid screenshots; automatic crop for other content may differ',
    'device_live_acceptance':'unverified',
}


def ipad_composition(source_size,subject_box=None,multiplier=1,margin=.05,fit='crop',anchor=(.5,.38),zoom=1):
    """Full-bleed composition with focal point aligned to measured shared center.
    Crop preserves proportions; stretch scales axes independently. Neither mode
    places a small inset on a blurred background. Device crop remains empirical.
    """
    import math
    sw,sh=source_size
    if not all(math.isfinite(v) and v>0 for v in (sw,sh)):raise ValueError('Invalid source dimensions')
    if type(multiplier) is not int or not 1<=multiplier<=3:raise ValueError('Square export multiplier must be 1, 2 or 3')
    if fit not in ('crop','stretch'):raise ValueError('Unknown full-bleed fit')
    ax,ay=anchor
    if not all(math.isfinite(v) for v in (ax,ay,zoom)) or not .1<=ax<=.9 or not .1<=ay<=.9 or not 1<=zoom<=2:
        raise ValueError('Focus must be 10–90%, zoom must be 1–2')
    if subject_box is not None:
        bx,by,bw,bh=subject_box
        if min(bx,by)<0 or min(bw,bh)<=0 or bx+bw>sw or by+bh>sh:raise ValueError('Subject box must be inside source')
        ax,ay=(bx+bw/2)/sw,(by+bh/2)/sh
        if not .1<=ax<=.9 or not .1<=ay<=.9:raise ValueError('Subject center too close to edge')
    edge=2420*multiplier
    x,y,w,h=[v*multiplier for v in IPAD_PROFILE['shared_rect']]
    cx,cy=x+w/2,y+h/2
    if fit=='stretch':
        # Piecewise affine full-frame warp: preserve all four edges, map the
        # chosen source focal point to the measured common-view center.
        # No inset, no transparent edges and no extra crop to shift the anchor.
        if zoom!=1:raise ValueError('Stretch full-frame uses zoom=1')
        cw,ch=math.ceil(sw/2)*2,math.ceil(sh/2)*2
        sx=max(2,min(cw-2,round(cw*ax/2)*2));sy=max(2,min(ch-2,round(ch*ay/2)*2))
        tx,ty=round(cx/2)*2,round(cy/2)*2
        sources=[[0,0,sx,sy],[sx,0,cw-sx,sy],[0,sy,sx,ch-sy],[sx,sy,cw-sx,ch-sy]]
        targets=[[0,0,tx,ty],[tx,0,edge-tx,ty],[0,ty,tx,edge-ty],[tx,ty,edge-tx,edge-ty]]
        return {'canvas':[edge,edge],'source_size':[sw,sh],'coded_source_size':[cw,ch],
                'foreground_size':[edge,edge],'foreground_offset':[0,0],
                'target_center':[tx,ty],'safe_rect':[x,y,w,h],
                'source_tiles':sources,'target_tiles':targets,'fit':fit,'anchor':[ax,ay],
                'zoom':1,'multiplier':multiplier,'source_upsampled':edge>min(sw,sh),
                'preset_id':IPAD_PROFILE['id'],
                'meaning':'Full-frame piecewise stretch; all edges retained; proportions change; measured focal mapping, not system auto-relayout'}
    need_w=max(cx/ax,(edge-cx)/(1-ax))*zoom
    need_h=max(cy/ay,(edge-cy)/(1-ay))*zoom
    if fit=='crop':
        scale=max(need_w/sw,need_h/sh);need_w,need_h=sw*scale,sh*scale
    fw,fh=math.ceil(need_w/2)*2,math.ceil(need_h/2)*2
    if max(fw,fh)>16384 or fw*fh>100_000_000:raise ValueError('Focus/zoom exceeds render pixel budget')
    ox,oy=round(cx-fw*ax),round(cy-fh*ay)
    ox=max(edge-fw,min(0,ox));oy=max(edge-fh,min(0,oy))
    return {'canvas':[edge,edge],'source_size':[sw,sh],'foreground_size':[fw,fh],
            'foreground_offset':[ox,oy],'target_center':[cx,cy],'safe_rect':[x,y,w,h],
            'fit':fit,'anchor':[ax,ay],'zoom':zoom,'multiplier':multiplier,
            'source_upsampled':fw>sw or fh>sh,'preset_id':IPAD_PROFILE['id'],
            'meaning':'Full-bleed measured focal alignment; stretch distorts proportions, crop trims edges; not system auto-relayout'}


def _ipad_filter(layout,sharpen=0,static=False):
    import math
    if not math.isfinite(sharpen) or not 0<=sharpen<=1:raise ValueError('Invalid sharpen: choose 0–1')
    tail=(f',unsharp=5:5:{sharpen:g}:5:5:0' if sharpen else '')+(',format=rgb24[out]' if static else ',format=yuv420p[out]')
    if layout['fit']=='stretch':
        cw,ch=layout['coded_source_size']
        parts=[f'scale={cw}:{ch}:flags=lanczos,split=4[s0][s1][s2][s3]']
        for i,(source,target) in enumerate(zip(layout['source_tiles'],layout['target_tiles'])):
            x,y,w,h=source;_,_,tw,th=target
            parts.append(f'[s{i}]crop={w}:{h}:{x}:{y},scale={tw}:{th}:flags=lanczos,setsar=1[t{i}]')
        parts.extend(['[t0][t1]hstack=inputs=2[top]','[t2][t3]hstack=inputs=2[bottom]','[top][bottom]vstack=inputs=2,setsar=1'+tail])
        return ';'.join(parts)
    edge=layout['canvas'][0];fw,fh=layout['foreground_size'];x,y=layout['foreground_offset']
    return f'scale={fw}:{fh}:flags=lanczos,crop={edge}:{edge}:{-x}:{-y},setsar=1'+tail


_context = threading.local()
def _lab_run(command,timeout=300):
    from .source import run_tool
    cancel=getattr(_context,'cancel',None)
    progress=getattr(_context,'progress',None)
    _context.step=getattr(_context,'step',0)+1
    if progress: progress(min(94,5+_context.step*7),'iPad 导出 · 正在编码或校验，请稍候…')
    return run_tool([str(x) for x in command],cancel=cancel,timeout=timeout)


def motion_jpeg_payload(data):
    """Observed Honor envelope only; plain JPEGs never become fake motion."""
    import re
    data=bytes(data)
    if not data.startswith(b'\xff\xd8'):return None
    tag=data.rfind(b'HiHonor_ExtInfo')
    if tag<0:return None
    marker=re.search(rb'LIVE_(\d+)\s*$',data[-128:])
    if marker is None:raise ValueError('Incomplete Honor motion JPEG trailer')
    index=data.find(b'ftyp',tag+len(b'HiHonor_ExtInfo'),tag+96)
    if index<4:raise ValueError('Missing Honor movie signature')
    start=index-4;end=start+_valid_movie_end(data[start:]);payload=data[start:end]
    if not payload or len(payload)+20!=int(marker.group(1)):
        raise ValueError('Honor movie length disagrees with trailer')
    return payload

def _file_sha256(path):
    import hashlib
    digest=hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def _export_ipad(source,output,ffmpeg,ffprobe,start=0,subject_box=None,multiplier=1,margin=.05,cover_time=.5,fit='crop',anchor=(.5,.38),zoom=1,static_frame=False,sharpen=0):
    """Independent file exporter. Static input stays static; motion is never invented."""
    import hashlib,shutil,math
    from PIL import Image,ImageOps
    source=Path(source).resolve();output=Path(output).resolve()
    if not source.is_file():raise FileNotFoundError(source)
    if output==source or source in output.parents:raise ValueError('Output overlaps source')
    if output.exists():raise FileExistsError('Choose a new output folder')
    if not math.isfinite(start) or start<0:raise ValueError('Invalid clip start')
    _register_heif();source_hash=_file_sha256(source)
    output.mkdir(parents=True);inputs=output/'inputs';inputs.mkdir()
    staged=inputs/('source'+source.suffix.lower());shutil.copy2(source,staged)
    assert _file_sha256(staged)==source_hash
    ffmpeg,ffprobe=Path(ffmpeg).resolve(),Path(ffprobe).resolve()
    static=source.suffix.lower() in ('.jpg','.jpeg','.png','.webp','.heic','.heif','.bmp')
    if staged.suffix in ('.jpg','.jpeg'):
        motion=motion_jpeg_payload(staged.read_bytes())
        if motion is not None:
            staged=inputs/'embedded.mp4';staged.write_bytes(motion);static=False
    if staged.suffix in ('.heic','.heif'):
        try:still,motion=split_hybrid(staged.read_bytes())
        except ValueError:pass
        else:
            staged=inputs/'embedded.mov';staged.write_bytes(motion);static=False
    try:
        if static:
            if start!=0:raise ValueError('Static images do not have a clip start')
            with Image.open(staged) as im:
                if getattr(im,'n_frames',1)>1:raise ValueError('Animated image input requires conversion to video first')
                image=ImageOps.exif_transpose(im).convert('RGB');image.save(output/'source-frame.png');size=image.size
            probe={};media_source=output/'source-frame.png'
        else:
            probe=json.loads(_lab_run([ffprobe,'-v','error','-show_streams','-show_format','-of','json',staged]))
            stream=next((v for v in probe.get('streams',[]) if v['codec_type']=='video'),None)
            if stream is None:raise ValueError('Input has no video stream')
            duration=float(stream.get('duration',probe.get('format',{}).get('duration',0)))
            if not math.isfinite(duration) or (duration<=start if static_frame else duration<start+1-1e-6):
                raise ValueError('Select a full one-second source interval; video is never looped')
            _lab_run([ffmpeg,'-v','error','-i',staged,'-ss',start,'-frames:v','1',output/'source-frame.png'])
            with Image.open(output/'source-frame.png') as im:size=im.size
            media_source=staged
            if static_frame:static=True;media_source=output/'source-frame.png'
        layout=ipad_composition(size,subject_box,multiplier,margin,fit,anchor,zoom)
        filt=_ipad_filter(layout,sharpen=sharpen,static=static);identifier=str(uuid.uuid4()).upper()
        if static:
            _lab_run([ffmpeg,'-v','error','-i',media_source,'-filter_complex',filt,'-map','[out]','-frames:v','1',output/'wallpaper.png'])
            files=['wallpaper.png'];kind='static'
            if not static_frame:
                with Image.open(output/'wallpaper.png') as im:
                    im.save(output/'wallpaper.heic',format='HEIF',quality=90,color_primaries=1,transfer_characteristic=13,matrix_coefficients=1)
                files.append('wallpaper.heic')
        else:
            _lab_run([ffmpeg,'-v','error','-ss',start,'-i',media_source,'-f','lavfi','-t','1','-i','anullsrc=channel_layout=stereo:sample_rate=44100',
                      '-filter_complex',f'[0:v]setpts=PTS-STARTPTS,fps=60,{filt}','-map','[out]','-map','1:a','-t','1','-c:v','libx265','-preset','fast','-crf','20',
                      '-tag:v','hvc1','-x265-params','pools=4:frame-threads=2:log-level=error','-c:a','aac','-movie_timescale','600',output/'live.mov'])
            final=json.loads(_lab_run([ffprobe,'-v','error','-show_streams','-of','json',output/'live.mov']))
            video=next(v for v in final['streams'] if v['codec_type']=='video')
            if int(video.get('nb_frames',0))!=60 or video['avg_frame_rate']!='60/1':raise ValueError('Decoded source did not yield the required 60-frame one-second output')
            _lab_run([ffmpeg,'-v','error','-i',output/'live.mov','-vf',f'select=eq(n\\,{round(cover_time*60)})','-frames:v','1',output/'wallpaper.png'])
            with Image.open(output/'wallpaper.png') as im:im.save(output/'live.jpg',quality=95)
            write_photo(output/'live.jpg',identifier)
            with Image.open(output/'live.jpg') as im:
                im.save(output/'live.heic',format='HEIF',quality=90,exif=im.info['exif'],color_primaries=1,transfer_characteristic=13,matrix_coefficients=1)
            edge=layout['canvas'][0]
            template_motion(output/'live.mov',None,identifier,edge,edge,cover_time)
            pack_files(output/'live.heic',output/'live.mov',output/'wallpaper-live.heic')
            pack_livp(output/'live.heic',output/'live.mov',output/'wallpaper-live.livp')
            _lab_run([ffmpeg,'-v','error','-i',output/'live.mov','-map','0:v:0','-map','0:a:0','-c','copy',output/'preview.mp4'])
            _lab_run([ffmpeg,'-v','error','-i',output/'live.mov','-map','0:v:0','-f','null','-'])
            packets=json.loads(_lab_run([ffprobe,'-v','error','-select_streams','d','-show_packets','-of','json',output/'live.mov']))['packets']
            info=[v for v in packets if v['size']=='144'];marker=[v for v in packets if v['size']=='89']
            if len(info)!=57 or len(marker)!=1 or abs(float(marker[0]['pts_time'])-cover_time)>1e-6:
                raise ValueError('Timed metadata verification failed')
            files=['wallpaper.png','wallpaper-live.heic','wallpaper-live.livp','live.heic','live.mov','preview.mp4'];kind='motion'
        # These are previews of ONE exported square, not separate wallpaper assets.
        with Image.open(output/'wallpaper.png') as im:
            for orientation in ('landscape','portrait'):
                x,y,w,h=[v*multiplier for v in IPAD_PROFILE[orientation+'_rect']]
                left,top=max(0,round(x)),max(0,round(y));right,bottom=min(im.width,round(x+w)),min(im.height,round(y+h))
                target=(1210,834) if orientation=='landscape' else (834,1210)
                im.crop((left,top,right,bottom)).resize(target,Image.Resampling.LANCZOS).save(output/(orientation+'-preview.png'))
        result={'preset':IPAD_PROFILE,'kind':kind,'composition':layout,'source_sha256':source_hash,
                'source_start_seconds':start,'source_average_fps':next((v.get('avg_frame_rate') for v in probe.get('streams',[]) if v['codec_type']=='video'),None),
                'motion_profile':{'seconds':1,'fps':60,'cover_frame':round(cover_time*60),'cover_time':cover_time,'audio':'silent AAC','frame_conversion':'CFR conversion may duplicate source frames; no new source motion claimed'} if not static else None,
                'files':files,'device_acceptance':'unverified','preview_scope':'Measured crop-model simulation; actual Apple selection may change with content',
                'output_sha256':{name:_file_sha256(output/name) for name in files}}
        fw,fh=layout['foreground_size'];sw,sh=size;edge=layout['canvas'][0]
        result['quality']={'resampling':'Lanczos','sharpen':sharpen,'sharpen_scope':'luma only; no chroma sharpening','detail_recovery':'none','source_crop_size':[edge*sw/fw,edge*sh/fh],'scale_xy':[fw/sw,fh/sh],'lossless_upscale':False,'output_multiplier':multiplier}
        if _file_sha256(source)!=source_hash:raise RuntimeError('Source changed during export')
        (output/'export.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
        with zipfile.ZipFile(output/'ipad-export.zip','x',zipfile.ZIP_DEFLATED) as z:
            for name in files+['export.json','landscape-preview.png','portrait-preview.png']:z.write(output/name,name)
        with zipfile.ZipFile(output/'ipad-export.zip') as z:
            if z.testzip() is not None:raise ValueError('Export archive CRC failed')
        # A windowed EXE may have no stdout.
        if sys.stdout: print('iPad export: '+kind+'; packaging verified',flush=True)
        return result
    except BaseException as exc:
        (output/'FAILED.txt').write_text(str(exc),encoding='utf8');raise



def export_ipad(source,output,settings=None,cancel=None,progress=None,multiplier=1,work_root=None,fit='crop',anchor=(.5,.38),zoom=1,package='heic',sharpen=0):
    from .media import ffmpeg_path
    from .source import assert_output_outside_source,check_cancel
    import math
    if not math.isfinite(sharpen) or not 0<=sharpen<=1:raise ValueError('Invalid sharpen: choose 0–1')
    source,output=Path(source),Path(output)
    assert_output_outside_source(source,output)
    import os,tempfile,shutil
    if package not in ('heic','livp','honor','png'):raise ValueError('Unknown iPad package')
    if output.exists():raise FileExistsError('Choose a new output folder')
    work_root=Path(work_root) if work_root is not None else Path(os.getenv('LOCALAPPDATA',str(Path.home())))/'WallpaperStudio'/'jobs'/'ipad-export'
    assert_output_outside_source(source,work_root)
    start=0;cover_time=.5
    if settings is not None:
        import math
        left,right,cover=settings.start,settings.end,settings.cover
        if package=='png':
            if right is None or right<=left or not left<=cover<right:raise ValueError('请把封面设置在有效选区内')
            from .media import frame_timestamps
            timestamps=frame_timestamps(source,cancel=cancel)
            candidates=[t for t in timestamps if left<=t<right]
            if not candidates:raise ValueError('选区内没有解码帧')
            start=min(candidates,key=lambda t:abs(t-cover))
        elif right is None or right-left < 1-1e-6:
            raise ValueError('iPad 动态图需要至少 1 秒的选区；不会循环补帧')
        if package!='png':
            if not left<=cover<right:raise ValueError('请把封面设置在选区内')
            from .media import frame_timestamps
            timestamps=frame_timestamps(source,cancel=cancel)
            actual_cover=min((t for t in timestamps if left<=t<right),key=lambda t:abs(t-cover))
            desired=max(left,min(right-1,actual_cover-.5))
            candidates=[t for t in timestamps if left<=t<=right-1+1e-6]
            if not candidates:raise ValueError('选区内没有完整一秒的解码帧区间')
            start=min(candidates,key=lambda t:abs(t-desired))
            cover_time=round((actual_cover-start)*60)/60
            if not 0<=cover_time<=59/60:raise ValueError('封面过于接近片段终点，请向前移动一帧')
    _context.cancel=cancel;_context.progress=progress;_context.step=0
    try:
        check_cancel(cancel)
        if progress:progress(5,'正在复制素材并应用 iPad 实测构图…')
        work_root.mkdir(parents=True,exist_ok=True)
        work=Path(tempfile.mkdtemp(prefix='job-',dir=work_root))/'render'
        result=_export_ipad(source,work,ffmpeg_path(),ffmpeg_path().with_name('ffprobe.exe'),start=start,multiplier=multiplier,cover_time=cover_time,fit=fit,anchor=anchor,zoom=zoom,static_frame=package=='png',sharpen=sharpen)
        check_cancel(cancel)
        if result['kind']=='motion':
            validation=validate_ipad_pair(work/'live.heic',work/'live.mov')
            result.update(photo=work/'live.heic',video=work/'live.mov',single_file=work/'wallpaper-live.heic',livp=work/'wallpaper-live.livp',zip=work/'ipad-export.zip',validation=validation,ipad=True)
        check_cancel(cancel)
        if result['kind']=='motion' and package=='honor':
            from .motionphoto import export_honor_video
            android=export_honor_video(work/'live.mov',work,result['motion_profile']['cover_time'],cancel)
            result.update(photo=android['photo'],video=android['video'],validation=android['validation'],android=True,android_profile={'codec':'HEVC','fps':30,'cover_ms':android['validation']['cover_ms'],'device_acceptance':'unverified'})
            chosen=android['file']
        else:chosen=work/('wallpaper.png' if result['kind']=='static' else 'wallpaper-live.'+package)
        output.mkdir(parents=True,exist_ok=False)
        final=output/chosen.name
        try:
            with chosen.open('rb') as src,final.open('xb') as dst:
                while chunk:=src.read(1024*1024):
                    check_cancel(cancel);dst.write(chunk)
            if _file_sha256(chosen)!=_file_sha256(final):raise RuntimeError('Final output hash mismatch')
            check_cancel(cancel)
        except BaseException:
            if final.is_file():final.unlink()
            if not any(output.iterdir()):output.rmdir()
            raise
        result.update(final_file=final,output_dir=output,work_dir=work.parent)
        if result['kind']=='motion':result['single_file']=final
        (work/'published.json').write_text(json.dumps({'final_file':str(final),'sha256':_file_sha256(final)},indent=2),encoding='utf8')
        if progress:progress(100,'只导出一个最终文件 · '+final.name)
        return result
    finally:
        _context.cancel=None;_context.progress=None


def validate_ipad_pair(photo,movie):
    _register_heif()
    identifier=_photo_identifier(Path(photo));data=Path(movie).read_bytes()
    if movie_identifier(data)!=identifier:raise ValueError('Pair identifiers do not match')
    tracks=_sample_tracks(data)
    info=[s for d,s in tracks if b'live-photo-info' in d]
    marker=[s for d,s in tracks if b'still-image-time' in d]
    if len(info)!=1 or len(info[0])!=57 or len(marker)!=1 or len(marker[0])!=1:
        raise ValueError('Missing timed motion metadata samples')
    from .media import ffmpeg_path
    probe=json.loads(_lab_run([ffmpeg_path().with_name('ffprobe.exe'),'-v','error','-select_streams','d','-show_packets','-of','json',movie]))
    marks=[p for p in probe['packets'] if p['size']=='89']
    if len(marks)!=1:raise ValueError('Missing still-image-time packet')
    return {'valid':True,'identifier':identifier,'still_image_time':float(marks[0]['pts_time']),'device_acceptance':'unverified','profile':'experimental-reference-metadata'}
