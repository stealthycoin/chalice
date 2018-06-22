"""This module provides a watchdog and stat based file watching interface.

Watchdog does not appear to be maintained, does not have wheels available
and there are cases where it fails to install even if you have a compiler.
This module can be used as a replacement to ensure that local mode
functions as intended even if watchdog is not installed.

In order to serve as a replacement for watchdog this module wraps the watchdog
observer interface in a ``Watcher`` object. Two implementations are provided.
One that uses the prior watchdog event system. And a backup that simply uses
stat and mtime to check for changed files.

The long term plan is to tear out watchdog and replace it with something that
is better maintained and ideally has wheels available for all common platforms.
"""
