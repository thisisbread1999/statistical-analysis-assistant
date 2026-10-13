"""Execute the actual v2 notebook in explicit mock or real mode and save its outputs."""
import argparse
import os
from pathlib import Path
import nbformat
from nbclient import NotebookClient
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from scripts.notebook_artifacts import ASSIGNMENT_DIRECTORY, write_notebooks

parser = argparse.ArgumentParser()
parser.add_argument('--mode', choices=['mock', 'real'], required=True)
parser.add_argument('--output', help='Optional executed-notebook path; default overwrites the source notebook.')
parser.add_argument('--submission', action='store_true', help='Execute the standalone assignment from an empty working directory.')
args = parser.parse_args()
os.environ['LLM_MODE'] = args.mode
os.environ['PYTHONUTF8'] = '1'
runtime_dir = root / 'artifacts' / 'runtime' / 'jupyter_runtime'
runtime_dir.mkdir(parents=True, exist_ok=True)
# Keep temporary kernel connection files in the authorized project output folder.
import tempfile
tempfile.tempdir = str(runtime_dir)
os.environ['TMP'] = os.environ['TEMP'] = str(runtime_dir)
os.environ['JUPYTER_RUNTIME_DIR'] = str(runtime_dir)
os.environ['IPYTHONDIR'] = str(runtime_dir / 'ipython')
path = root / ASSIGNMENT_DIRECTORY / 'LangGraph_Submission.ipynb' if args.submission else root / 'demo.ipynb'
output_path = Path(args.output).resolve() if args.output else path
output_path.parent.mkdir(parents=True, exist_ok=True)
nb = nbformat.read(path, as_version=4)
# The current interpreter is used, avoiding an unrelated global Jupyter kernel.
from jupyter_client import KernelManager
km = KernelManager(kernel_name='python3')
km.kernel_spec.argv = [os.sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']
working_directory = runtime_dir / 'standalone_cwd' if args.submission else root
working_directory.mkdir(parents=True, exist_ok=True)
client = NotebookClient(nb, km=km, timeout=900, allow_errors=False,
                        resources={'metadata': {'path': str(working_directory)}})
def save_progress(cell, cell_index, **kwargs):
    nbformat.write(nb, output_path)
    print(f'Completed cell {cell_index + 1}/{len(nb.cells)}', flush=True)
client.on_cell_executed = save_progress
try:
    client.execute()
finally:
    nbformat.write(nb, output_path)
    if km.has_kernel:
        km.shutdown_kernel(now=True)
if not args.output and not args.submission:
    write_notebooks(root, nb)
elif not args.output and args.submission:
    import base64
    images = [output['data']['image/png'] for cell in nb.cells if cell.cell_type == 'code'
              for output in cell.get('outputs', []) if 'image/png' in output.get('data', {})]
    if not images:
        raise RuntimeError('Executed submission did not produce a graph image.')
    (root / ASSIGNMENT_DIRECTORY / 'graph.png').write_bytes(base64.b64decode(images[0]))
print(f'Executed and saved {output_path.name} in {args.mode} mode')
