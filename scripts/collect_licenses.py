"""Include installed dependency notices in both portable builds."""
from importlib.metadata import distributions
from pathlib import Path
import shutil

root=Path(__file__).resolve().parent.parent
dest=root/'licenses'; dest.mkdir(exist_ok=True)
for package in distributions():
    for path in package.files or []:
        if any(word in path.name.lower() for word in ('license','copying','notice','copyright')):
            source=Path(package.locate_file(path))
            if source.is_file():
                folder=dest/package.metadata['Name']; folder.mkdir(exist_ok=True)
                shutil.copy2(source,folder/(str(path).replace('/','_').replace('\\','_')))
shutil.copy2(root/'LICENSE',dest/'GPL-3.0.txt')
