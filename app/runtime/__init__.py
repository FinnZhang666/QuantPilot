"""Realtime runtime package.

Keep package import side-effect free so command and notification modules can
reuse runtime state without recursively importing the runtime process.
"""
