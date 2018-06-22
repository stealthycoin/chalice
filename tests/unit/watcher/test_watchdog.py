import threading

import pytest

from chalice.cli import reloader
from tests.conftest import watchdog_only


# NOTE: Fixtures are used here to hide the imports so these tests will not
# cause issues if watchdog is not installed.
@pytest.fixture
def watchdog_event_adapter():
    from chalice.watcher.eventbased import WatchDogEventAdapter

    def factory(handler):
        return WatchDogEventAdapter(handler)
    return factory


@pytest.fixture
def dir_mod_event():
    from watchdog.events import DirModifiedEvent

    def factory(src_path):
        return DirModifiedEvent(src_path=src_path)
    return factory


@pytest.fixture
def file_mod_event():
    from watchdog.events import FileModifiedEvent

    def factory(src_path):
        return FileModifiedEvent(src_path=src_path)
    return factory


@watchdog_only
def test_directory_events_ignored(watchdog_event_adapter, dir_mod_event):
    restart_event = threading.Event()
    restarter = reloader.Restarter(restart_event)
    adapter = watchdog_event_adapter(restarter)
    app_modified = dir_mod_event(src_path='./')
    adapter.on_any_event(app_modified)
    assert not restart_event.is_set()


@watchdog_only
def test_file_events_respected(watchdog_event_adapter, file_mod_event):
    restart_event = threading.Event()
    restarter = reloader.Restarter(restart_event)
    adapter = watchdog_event_adapter(restarter)
    app_modified = file_mod_event(src_path='./app.py')
    adapter.on_any_event(app_modified)
    assert restart_event.is_set()
