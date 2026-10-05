"""Wallpaper Engine exposed user properties; commands target owned windows only."""
from __future__ import annotations
import json, math
from pathlib import Path

SUPPORTED={'bool','slider','combo','color','textinput','file','directory'}

def read_properties(source):
    p=Path(source)
    p=p/'project.json' if p.is_dir() else p.parent/'project.json' if p.suffix.lower()!='.json' else p
    if not p.is_file(): return {}
    data=json.loads(p.read_text(encoding='utf-8-sig'))
    props=data.get('general',{}).get('properties',{})
    return dict(sorted(((k,v) for k,v in props.items() if isinstance(v,dict)),key=lambda item:item[1].get('order',0)))

def validate_values(schema, values):
    for key,value in values.items():
        if key not in schema: raise ValueError(f'未知壁纸选项：{key}')
        p=schema[key];kind=p.get('type')
        valid=False
        if kind=='bool': valid=isinstance(value,bool)
        elif kind=='slider': valid=isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and p.get('min',0)<=value<=p.get('max',100)
        elif kind=='combo': valid=any(value==option.get('value') for option in p.get('options',[]))
        elif kind=='color':
            try:
                parts=[float(v) for v in value.split()]
                valid=len(parts)==3 and all(math.isfinite(v) and 0<=v<=1 for v in parts)
            except (ValueError,AttributeError): pass
        elif kind in ('textinput','file','directory'): valid=isinstance(value,str)
        if not valid: raise ValueError(f'壁纸选项值无效：{key}')
    return dict(values)

def properties_command(engine, name, values):
    if not name.startswith('WallpaperStudio-'): raise ValueError('需要本工具的命名窗口')
    return [str(engine),'-control','applyProperties','-properties',
            'RAW~('+json.dumps(values,ensure_ascii=False,separators=(',',':'))+')~END','-location',name]

def prepare_properties(project, values):
    """Write defaults to the staged copy before opening; never the source."""
    if not values: return
    p=Path(project);p=p if p.name=='project.json' else p.parent/'project.json'
    schema=read_properties(p);validate_values(schema,values)
    data=json.loads(p.read_text(encoding='utf-8-sig'))
    for key,value in values.items(): data['general']['properties'][key]['value']=value
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
