from scraping_biwenger.players import value_history as _value_history

for _name in dir(_value_history):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_value_history, _name)

__all__ = [_name for _name in dir(_value_history) if not _name.startswith("__")]
