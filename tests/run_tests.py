import importlib.util
import traceback
import os
import sys

here = os.path.dirname(__file__)
# ensure repository root is on sys.path so test modules can import project modules
repo_root = os.path.abspath(os.path.join(here, '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

mod_path = os.path.join(here, 'test_simulation.py')
spec = importlib.util.spec_from_file_location('test_simulation', mod_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

failed = []
for name in dir(mod):
    if name.startswith('test_'):
        test_fn = getattr(mod, name)
        try:
            test_fn()
            print(f"PASS {name}")
        except Exception:
            print(f"FAIL {name}")
            traceback.print_exc()
            failed.append(name)

if failed:
    print(f"{len(failed)} tests failed: {failed}")
    raise SystemExit(1)
else:
    print("All tests passed")
