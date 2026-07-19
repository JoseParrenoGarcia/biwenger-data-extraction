from scraping_biwenger.players import detail_loop as _detail_loop

for _name in dir(_detail_loop):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_detail_loop, _name)

__all__ = [_name for _name in dir(_detail_loop) if not _name.startswith("__")]
