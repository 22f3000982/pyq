"""Package source, built UI, real fixtures and sanitized five-paper bank only."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
root=Path(__file__).resolve().parents[1];target=root.parent/'PYQ-Studio-Five-Paper-Demo.zip'
include=['backend','frontend/src','frontend/tests','frontend/dist','migrations','tests','scripts','sample-data','data','docs']
files=[]
for name in include:files.extend(p for p in (root/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts)
for name in ['README.md','requirements.txt','Dockerfile','compose.yaml','.env.example','.gitignore','.dockerignore','demo-papers.json','frontend/package.json','frontend/package-lock.json','frontend/index.html','frontend/vite.config.js','frontend/vitest.config.js']:
 p=root/name
 if p.exists():files.append(p)
with ZipFile(target,'w',ZIP_DEFLATED) as z:
 for p in sorted(set(files)):z.write(p,'pyq-platform/'+p.relative_to(root).as_posix())
with ZipFile(target) as z:
 assert z.testzip() is None
 assert not any(x.endswith('/.env') or '/instance/' in x or '/node_modules/' in x or '__pycache__' in x for x in z.namelist())
print(target,round(target.stat().st_size/1024/1024,2),'MiB',len(files),'files')
