#!/usr/bin/env python3
"""
JAM Preimages STF Tests - Python Implementation
Main entry point for running preimage tests.
"""

import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.index import main

if __name__ == "__main__":
    main()
