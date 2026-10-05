"""Prepare auditable source and friendly release assets; never uploads anything."""
from pathlib import Path
import argparse, hashlib, re, shutil, zipfile

ROOT_FILES = {'.gitignore','README.md','LICENSE','THIRD_PARTY_NOTICES.md','pyproject.toml','requirements-lock.txt','tools-manifest.json'}
ROOT_DIRS = {'.github','wallpaper_studio','scripts','tests','docs','licenses'}
SUFFIXES = {'.py','.ps1','.md','.txt','.yml','.yaml','.json','.toml','.html','.rst','.cff'}

def public_files(root):
 root=Path(root).resolve();files=[]
 for p in root.rglob('*'):
  rel=p.relative_to(root)
  if rel.parts[0] not in ROOT_DIRS and str(rel) not in ROOT_FILES:continue
  if not p.is_file() or p.is_symlink() or '__pycache__' in rel.parts:continue
  license_file=rel.parts[0]=='licenses' and any(word in p.name.upper() for word in ('LICENSE','COPYING','NOTICE'))
  if p.suffix.lower() not in SUFFIXES and p.name not in ROOT_FILES and not license_file:continue
  if p.stat().st_size>10_000_000:raise ValueError('Unexpected large source file: '+str(rel))
  text=p.read_text(encoding='utf-8-sig')
  for pattern,label in ((r'[A-Z]:[/\\]+Users[/\\]+[^/\\\s]+','personal path'),(r'gh[pousr]_[A-Za-z0-9]{20,}','token'),(r'github_pat_[A-Za-z0-9_]{20,}','token'),(r'sk-[A-Za-z0-9_-]{24,}','possible key')):
   if re.search(pattern,text,re.I):raise ValueError(label+' in '+str(rel))
  files.append(rel.as_posix())
 return sorted(files)

def prepare(root,version):
 root=Path(root).resolve();dist=root/'dist'/('v'+version);out=dist/'release'
 files=public_files(root)
 portable=dist/f'WallpaperStudio-{version}-win64.zip';exe=dist/'onefile/WallpaperStudio.exe'
 if not portable.is_file() or not exe.is_file():raise FileNotFoundError('Build both portable and onefile first')
 out.mkdir(exist_ok=True)
 names=[portable.name,f'WallpaperStudio-{version}-win64.exe',f'wallpaper-studio-{version}-source.zip']
 shutil.copy2(portable,out/names[0]);shutil.copy2(exe,out/names[1])
 with zipfile.ZipFile(out/names[2],'w',zipfile.ZIP_DEFLATED) as z:
  for name in files:z.write(root/name,f'wallpaper-studio-{version}/{name}')
 with zipfile.ZipFile(out/names[2]) as z:
  if z.testzip() is not None:raise ValueError('Source archive CRC failed')
 sums=[]
 for name in names:
  h=hashlib.sha256()
  with (out/name).open('rb') as f:
   for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
  sums.append(h.hexdigest()+'  '+name)
 (out/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf8')
 shutil.copy2(root/'docs/RELEASE_NOTES.md',out/'RELEASE_NOTES.md')
 print(f'release_assets=5; audited_source_files={len(files)}; source_crc=PASS; uploaded=False')
 return out

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--version',required=True);args=parser.parse_args()
 print(prepare(Path(__file__).resolve().parents[1],args.version))
