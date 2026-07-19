from scraping_biwenger.players import detail as _detail

for _name in dir(_detail):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_detail, _name)

__all__ = [_name for _name in dir(_detail) if not _name.startswith("__")]
