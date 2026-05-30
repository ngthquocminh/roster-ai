"""Make the backend package root importable when running pytest from anywhere."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
