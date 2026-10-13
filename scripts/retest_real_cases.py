"""Rerun only cases affected by a verified prompt/placeholder conflict, retaining first-run evidence."""
from pathlib import Path
import json, os, sys, nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
import tempfile
root=Path(__file__).resolve().parents[1]
runtime=root/'artifacts'/'runtime'/'jupyter_runtime'; runtime.mkdir(parents=True, exist_ok=True)
os.environ.update(LLM_MODE='real',PYTHONUTF8='1',TMP=str(runtime),TEMP=str(runtime),JUPYTER_RUNTIME_DIR=str(runtime),IPYTHONDIR=str(runtime/'ipython'))
tempfile.tempdir=str(runtime)
source=nbformat.read(root/'demo.ipynb',as_version=4)
# Setup, shared synthetic design/show helper, and exactly the two affected examples.
selected=[]
for i,c in enumerate(source.cells):
    if c.cell_type!='code': continue
    if 'agent_a, agent_b, configuration = create_agents()' in c.source or 'TUTORING_DESIGN = {' in c.source or c.source.startswith('pearson = show_case') or c.source.startswith('regression = show_case'):
        selected.append(nbformat.v4.new_code_cell(c.source))
assert len(selected)==4
selected.append(nbformat.v4.new_code_cell('''from datetime import datetime, timezone
verification = {"executed_at": datetime.now(timezone.utc).isoformat(), "configuration": configuration,
                "cases": case_outputs, "reason": "Retest after adding protected null/decision/direction fields and distinguishing null hypotheses from estimated slopes."}
(OUTPUT_DIR / "v2_targeted_real_evidence.json").write_text(json.dumps(verification,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
print([(k,v["status"],v["revisions"]) for k,v in case_outputs.items()])'''))
nb=nbformat.v4.new_notebook(cells=selected,metadata=source.metadata)
km=KernelManager(kernel_name='python3'); km.kernel_spec.argv=[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}']
client=NotebookClient(nb,km=km,timeout=900,allow_errors=False,resources={'metadata':{'path':str(root)}})
out=root/'artifacts'/'runtime'/'v2_targeted_real.ipynb'
def progress(cell,cell_index,**kwargs):
    nbformat.write(nb,out); print('Completed targeted cell',cell_index+1,flush=True)
client.on_cell_executed=progress
try: client.execute()
finally:
    nbformat.write(nb,out)
    if km.has_kernel: km.shutdown_kernel(now=True)
