from pathlib import Path
from importlib.util import module_from_spec, spec_from_file_location
spec=spec_from_file_location('shared_merchant_traffic',Path(__file__).resolve().parents[1]/'d5027-fast-0235'/'traffic.py')
shared=module_from_spec(spec)
spec.loader.exec_module(shared)
next_slot_at=shared.next_slot_at
