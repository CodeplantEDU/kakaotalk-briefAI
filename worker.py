import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).with_name('bridge_worker.py')), run_name='__main__')
