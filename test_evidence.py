import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from app.evidence import evidence_service

ev = evidence_service.get_evidence("p718-pb14-quality-status") # I need to guess the exact slug, wait, let me search for the file.
