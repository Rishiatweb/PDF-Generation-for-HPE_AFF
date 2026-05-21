"""Dataset downloaders.

Each module ingests one external source into ``data/raw/<source>/``.
Modules are intentionally independent: no shared base class, no plugin
registry — adding a new source means adding a new file here.
"""
