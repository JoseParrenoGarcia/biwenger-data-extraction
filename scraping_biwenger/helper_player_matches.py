from scraping_biwenger.players import matches as _matches

for _name in dir(_matches):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_matches, _name)

__all__ = [_name for _name in dir(_matches) if not _name.startswith("__")]
