from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from watchdog.events import FileSystemEvent  # noqa

from chalice.watcher.shared import Watcher

from typing import Callable  # noqa


class WatchDogEventAdapter(FileSystemEventHandler):
    """Filters out watchdog directory evnets."""
    def __init__(self, handler):
        # type: (Callable) -> None
        self._handler = handler

    def on_any_event(self, event):
        # type: (FileSystemEvent) -> None
        if event.is_directory:
            return
        self._handler()


class WatchdogFileWatcher(Watcher):
    """Uses watchdog to watch files for changes."""
    def start_watching(self, handler, path):
        # type: (Callable, str) -> None
        observer = Observer()
        watchdog_adapter = WatchDogEventAdapter(handler)
        observer.schedule(watchdog_adapter, path, recursive=True)
        observer.start()
