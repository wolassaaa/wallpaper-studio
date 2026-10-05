"""Local-only integration: select real samples, copy them, verify originals.

Never uploads user media. All reports and outputs are below test-workspace.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from wallpaper_studio.source import discover_library,hash_manifest,stage_project
from wallpaper_studio.models import EditSettings,CaptureSettings
from wallpaper_studio.media import probe,frame_timestamps,extract_frame,export_video,export_gif
from wallpaper_studio.livephoto import export_live_photo,validate_pair
from wallpaper_studio.capture import capture_scene,capture_still


def package_scene(path):
    with path.open('rb') as f:
        def integer(): return struct.unpack('<i',f.read(4))[0]
        def string(): return f.read(integer()).decode('utf-8')
        string(); entries=[]
        for _ in range(integer()): entries.append((string(),integer(),integer()))
        base=f.tell()
        scene=next((e for e in entries if e[0]=='scene.json'),None)
        if not scene: return {}
        f.seek(base+scene[1]); return json.loads(f.read(scene[2]))


def select_samples(entries):
    selected={}
    for entry in entries:
        root=entry.source
        size=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
        if size>90*1024*1024: continue
        if entry.kind=='video' and 'video' not in selected: selected['video']=entry
        elif entry.kind=='web' and 'web' not in selected: selected['web']=entry
        elif entry.kind=='scene':
            package=root/'scene.pkg'
            try:
                scene=package_scene(package) if package.exists() else json.loads((entry.wallpaper_file).read_text(encoding='utf-8-sig'))
                objects=scene.get('objects',[])
                dynamic=any(o.get('particle') or o.get('effects') for o in objects)
                category='dynamic_scene' if dynamic else 'plain_scene'
                selected.setdefault(category,entry)
                if 'gif' in str(entry.wallpaper_file).lower(): selected.setdefault('animated_scene',entry)
            except Exception: continue
        if all(k in selected for k in ('video','web','plain_scene','dynamic_scene','animated_scene')): break
    return selected


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--hardware',action='store_true'); parser.add_argument('--high-res',action='store_true')
    args=parser.parse_args(); root=Path(__file__).resolve().parent.parent/'test-workspace'/'integration'
    root.mkdir(parents=True,exist_ok=True)
    selected=select_samples(discover_library(args.library)); results=[]
    for category,entry in selected.items():
        before=hash_manifest(entry.source); record={'category':category,'title':entry.title,'source_id':entry.source.name,'tested_actions':['verified_copy']}
        try:
            copied=stage_project(entry.source,root/'copies')
            source=copied/(entry.wallpaper_file.relative_to(entry.source))
            outputs=root/category; outputs.mkdir(exist_ok=True)
            if entry.kind=='video':
                record['tested_actions'].extend(['decode','exact_frame','mp4','gif','live_pair'])
                info=probe(source); record['source_info']=info
                end=min(info['duration'],4)
                settings=EditSettings(width=320,height=220,fit='crop',end=end,cover=min(1.5,end/2))
                pts=frame_timestamps(source)
                extract_frame(source,outputs/'frame.png',len(pts)//2,settings)
                export_video(source,outputs/'clip.mp4',settings)
                export_gif(source,outputs/'clip.gif',settings)
                if end>=3:
                    pair=export_live_photo(source,outputs/'live',settings)
                    record['live']=validate_pair(pair['photo'],pair['video'])
                record['export_info']=probe(outputs/'clip.mp4')
            elif args.hardware:
                record['tested_actions'].append('native_wgc_record')
                record['capture']=capture_scene(source,outputs/'capture.mp4',CaptureSettings(width=640,height=360,seconds=1,wait=20),progress=lambda n,m:print(category,n,m,flush=True))
                record['decoded']=probe(outputs/'capture.mp4')
                if args.high_res and category=='plain_scene':
                    record['resolution_checks']=[]
                    for width,height in ((2420,1668),(3840,2160),(7680,4320)):
                        image=outputs/f'check-{width}x{height}.png'
                        report=capture_still(source,image,CaptureSettings(width=width,height=height,wait=20),progress=lambda n,m:print(n,m,flush=True))
                        record['resolution_checks'].append(report)
            record['result']='PASS'
        except Exception as exc:
            record['result']='FAIL'; record['error']=repr(exc)
        finally:
            record['source_unchanged']=hash_manifest(entry.source)==before
            (root/f'{category}-source-manifest.json').write_text(json.dumps(before,indent=2),encoding='utf-8')
        results.append(record)
        print(json.dumps(record,ensure_ascii=False,default=str),flush=True)
        (root/'report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    return 0 if all(r['result']=='PASS' and r['source_unchanged'] for r in results) else 1

if __name__=='__main__': raise SystemExit(main())
