from scraping_biwenger.players import discover as _discover

for _name in dir(_discover):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_discover, _name)

__all__ = [_name for _name in dir(_discover) if not _name.startswith("__")]
