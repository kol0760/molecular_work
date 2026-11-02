#!/usr/bin/env python3
"""Offline admin config validation only. Never constructs SSHTransport."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.slurm import Config,SlurmAdapter
config=Config.load(ROOT/'.private/slurm.json')
print(json.dumps(SlurmAdapter(config,ROOT/'.private/slurm-receipts').connection(),indent=2))
