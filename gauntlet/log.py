import logging
import os

LOG_FILE = "gauntlet.log"


def setup_logging(level=logging.INFO, log_file=LOG_FILE):
    root = logging.getLogger("gauntlet")
    if root.handlers:
        return root
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)
    if log_file:
        try:
            fh = logging.FileHandler(os.fspath(log_file))
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError:
            root.warning("Could not open log file %s", log_file)
    return root
