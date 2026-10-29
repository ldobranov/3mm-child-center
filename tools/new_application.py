"""Create a standalone native-own-SQLite starter in a new directory. Never overwrite."""
import argparse
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
SHARED_TOOLS = ('check_application.py', 'application_process_check.py', 'check_local_frontend.mjs', 'Check-Application.ps1')

def create_application(output, module_id, name):
    output = Path(output)
    if not re.fullmatch(r'[a-z][a-z0-9]*(?:\.[a-z][a-z0-9-]*){2,}', module_id):
        raise ValueError('Use a reverse-domain module ID, e.g. org.example.application')
    if not name.strip() or len(name) > 120:
        raise ValueError('Application name must contain 1–120 characters')
    if output.exists() or output.is_symlink():
        raise ValueError('Output must be a new directory; existing files are never replaced')
    if not output.parent.is_dir():
        raise ValueError('Output parent directory must exist')
    shutil.copytree(ROOT/'templates/native-app', output, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache', '.runtime', 'node_modules'))
    (output/'tools').mkdir()
    for tool in SHARED_TOOLS:
        shutil.copyfile(ROOT/'tools'/tool, output/'tools'/tool)
    metadata = {'module_id':module_id, 'name':name.strip(), 'version':'1.0.0', 'wheel_version':'1.0.0'}
    (output/'application.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'.gitignore').write_text('.runtime/\nnode_modules/\n__pycache__/\n*.pyc\n.pytest_cache/\ndist/\n',encoding='utf-8')
    return output.resolve()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--module-id',required=True)
    parser.add_argument('--name',required=True)
    args=parser.parse_args()
    print(create_application(args.output,args.module_id,args.name))

if __name__=='__main__': main()
