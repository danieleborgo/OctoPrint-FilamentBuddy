"""
FilamentBuddy OctoPrint plugin
Copyright (C) 2024 Daniele Borgo
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import absolute_import

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock, Thread
from gpiozero import DigitalInputDevice
from flask import jsonify

import octoprint.plugin
from octoprint.events import Events

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal


class FilamentBuddyPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.EventHandlerPlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ShutdownPlugin,
    octoprint.plugin.SimpleApiPlugin
):
    BOUNCE_TIME = 1  # s
    VERIFYING_TIME = 1  # s

    def __init__(self):
        super().__init__()
        self.__fs_manager = None

    def on_after_startup(self):
        self.__reset_plugin()
        self._logger.info("Plugin ready")

    def on_shutdown(self):
        if self.__fs_manager is not None:
            self.__fs_manager.close()

    def __reset_plugin(self):
        self.initialize_filament_sensor()

    def initialize_filament_sensor(self):
        if self.__fs_manager is not None:
            self.__fs_manager.close()
        self.__fs_manager = None
        if not self.get_bool("fs", "en"):
            return

        if "polling".__eq__(self.get_string("fs", "sensor_mode")):
            self.__fs_manager = FilamentBuddyPlugin.PollingManager(
                self._logger,
                self.__runout_action,
                self.get_int("fs", "sensor_pin"),
                self.get_int("fs", "polling_time"),
                self.get_int("fs", "run_out_time"),
                self.get_string("fs", "empty_voltage")
            )
            self.__enable_if_printing()
            return

        if "interrupt".__eq__(self.get_string("fs", "sensor_mode")):
            self.__fs_manager = FilamentBuddyPlugin.InterruptManager(
                self._logger,
                self.__runout_action,
                self.get_int("fs", "sensor_pin"),
                self.get_int("fs", "run_out_time"),
                self.get_string("fs", "empty_voltage")
            )
            self.__enable_if_printing()
            return

        raise Exception("Implementation error: this FS type is unknown")

    def __runout_action(self):
        if self.get_bool("fs", "use_pause"):
            self._printer.pause_print()
        self._printer.commands(
            [c.strip() for c in self.get_string("fs", "run_out_command").split("\n")]
        )
        self.send_notification("The filament has run out", True)

    def __enable_if_printing(self):
        if self._printer.is_printing():
            self.__fs_manager.start_checking()

    def on_event(self, event, payload):
        if not event.startswith("Print"):
            return

        if Events.PRINT_STARTED.__eq__(event):
            if self.__fs_manager is not None:
                self.__fs_manager.start_checking()
            if not self.__fs_manager.is_currently_available():
                self.send_notification("Filament not found, starting run out timeout")
            if self.get_bool("fr", "en"):
                self.insert_filament()
            return

        if Events.PRINT_PAUSED.__eq__(event):
            if self.__fs_manager is not None:
                self.__fs_manager.stop_checking()
            return

        if Events.PRINT_RESUMED.__eq__(event):
            if self.__fs_manager is not None:
                self.__fs_manager.start_checking()
                if not self.__fs_manager.is_currently_available():
                    self.send_notification("Filament not found, starting run out timeout")
            return

        if event in (Events.PRINT_DONE, Events.PRINT_FAILED):
            if self.__fs_manager is not None:
                self.__fs_manager.stop_checking()
            if self.get_bool("fr", "en"):
                self.remove_filament()
            return

    def generate_fr_command(self, length, command):
        if "simplified".__eq__(self.get_string("fr", "command_mode")):
            c = ["G91", f"G1 E{length}", "G90"]
            if self.get_bool("fr", "force_cold"):
                c.insert(0, "M302 P1")
            return c
        return [c.strip() for c in command.split("\n")]

    def remove_filament(self):
        length = self.get_int("fr", "retract_length")
        if length <= 0:
            return
        commands = self.generate_fr_command(
            -length,
            self.get_string("fr", "retract_command")
        )
        self._printer.commands(commands)
        self._logger.info(f"Removing filament with: {commands}")

    def insert_filament(self):
        length = self.get_int("fr", "extrude_length")
        if length <= 0:
            return
        commands = self.generate_fr_command(
            length,
            self.get_string("fr", "extrude_command")
        )
        self._printer.commands(commands)
        self._logger.info(f"Inserting filament with: {commands}")

    def get_api_commands(self):
        return dict(
            filament_status=[]
        )

    def on_api_command(self, command, data):
        if command == "filament_status":
            return jsonify({
                'state': self.__fs_manager is not None,
                'filament': None if self.__fs_manager is None else self.__fs_manager.is_currently_available()
            })
        return None

    def send_notification(self, message: str, is_severe: bool = False):
        self._plugin_manager.send_plugin_message("filamentbuddy", {"message": message, "is_severe": is_severe})

    def get_raw_value(self, source: Literal["fc", "fs", "fr"], param):
        modified = self._settings.get([source])
        if param in modified:
            return modified[param]
        return FilamentBuddyPlugin.DEFAULT_SETTINGS[source][param]

    def get_int(self, source: Literal["fc", "fs", "fr"], param: str) -> int:
        return int(self.get_raw_value(source, param))

    def get_float(self, source: Literal["fc", "fs", "fr"], param: str) -> float:
        return float(self.get_raw_value(source, param))

    def get_bool(self, source: Literal["fc", "fs", "fr"], param: str) -> bool:
        return bool(self.get_raw_value(source, param))

    def get_string(self, source: Literal["fc", "fs", "fr"], param: str) -> str:
        return str(self.get_raw_value(source, param))

    DEFAULT_SETTINGS = {
        "first_startup": True,

        # Filament Changer
        "fc": {
            "en": False,
            "command_mode": "complete",
            "command": "g1",
            "force_cold": False,
            "filament_length": 50,  # mm
            "filament_speed": 500,  # mm/min
            "target_x": 0,  # mm
            "target_y": 0,  # mm
            "z_hop": 0,  # mm
            "unload_command": "G91\nG1 E-10\nG90",
            "load_command": "G91\nG1 E10\nG90",
            "use_unload": False,
            "min_tool_temp": 180  # °C
        },

        # Filament Sensor
        "fs": {
            "en": False,
            "sensor_pin": 8,
            "sensor_mode": "polling",
            "polling_time": 10,  # s
            "run_out_time": 60,  # s
            "use_pause": True,
            "run_out_command": "",
            "empty_voltage": "low",
            "toolbar_time": 4,  # s
            "toolbar_en": True
        },

        # Filament Remover
        "fr": {
            "en": False,
            "command_mode": "simplified",
            "retract_length": 20,  # mm
            "extrude_length": 0,  # mm
            "force_cold": False,
            "retract_command": "G91\nG1 E-10\nG90",
            "extrude_command": "",
            "use_unload": False
        }
    }

    def get_settings_defaults(self):
        return {
            **FilamentBuddyPlugin.DEFAULT_SETTINGS,
            **{
                "default": FilamentBuddyPlugin.DEFAULT_SETTINGS
            }
        }

    def on_settings_save(self, data):
        data["default"] = FilamentBuddyPlugin.DEFAULT_SETTINGS
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self.__reset_plugin()

    class FilamentSensorManager(ABC):

        def __init__(self, logger, runout_f):
            self.__pool = ThreadPoolExecutor(max_workers=1)
            self.__logger = logger
            self.__runout_f = runout_f

        @abstractmethod
        def start_checking(self):
            pass

        @abstractmethod
        def stop_checking(self):
            pass

        @abstractmethod
        def is_currently_available(self):
            pass

        @abstractmethod
        def close(self):
            pass

        def _submit(self, to_run):
            self.__pool.submit(to_run)

        def _close_pool(self):
            self.__pool.shutdown(wait=False)

        def _log(self, message: str):
            self.__logger.info(message)

        def _runout(self):
            self.__runout_f()

    class PollingManager(FilamentSensorManager):
        def __init__(self, logger, runout_f, pin: int, polling_time: int, runout_time: int, empty_v: str):
            super().__init__(logger, runout_f)
            self.__polling_time = polling_time
            self.__runout_time = runout_time
            self.__is_empty_high = "high".__eq__(empty_v.lower())

            self.__input_device = DigitalInputDevice(
                pin=pin,
                pull_up=self.__is_empty_high,
                bounce_time=FilamentBuddyPlugin.BOUNCE_TIME
            )
            self.__event = None
            self.__running = False
            self.__verifying = False

        def start_checking(self):
            if self.__running:
                return
            self.__running = True
            self.__event = Event()
            self._log("Filament Sensor via polling started")
            self._submit(self.__perform_polling)

        def stop_checking(self):
            if not self.__running:
                return
            self.__running = False
            self.__verifying = False
            self.__event.set()
            self._log("Filament Sensor via polling stopped")

        def __perform_polling(self):
            while self.__running:
                self.__event.wait(self.__polling_time)
                if not self.__running:
                    break

                # if the filament becomes unavailable
                if not self.is_currently_available():
                    self.__verifying = True
                    count = 0
                    self.__event.wait(FilamentBuddyPlugin.VERIFYING_TIME)
                    self._log("First missing filament")
                    while self.__verifying:
                        if self.is_currently_available():
                            # the filament came back before the deadline
                            self.__verifying = False
                            self._log("Filament has returned")
                            continue
                        if count * FilamentBuddyPlugin.VERIFYING_TIME >= self.__runout_time:
                            self._log("Run out time passed, printer paused")
                            self._runout()
                            self.stop_checking()
                            return
                        count += 1
                        self.__event.wait(FilamentBuddyPlugin.VERIFYING_TIME)

        def is_currently_available(self):
            return self.__input_device.value

        def close(self):
            if self.__running:
                self.stop_checking()
            self.__input_device.close()
            self._close_pool()
            self._log("Closed polling")

    class InterruptManager(FilamentSensorManager):
        def __init__(self, logger, runout_f, pin: int, runout_time: int, empty_v: str):
            super().__init__(logger, runout_f)
            self.__pin = pin
            self.__runout_time = runout_time
            self.__is_empty_high = "high".__eq__(empty_v.lower())

            self.__input_device = DigitalInputDevice(
                pin=pin,
                pull_up=self.__is_empty_high
            )
            self.__running = False
            self.__lock = Lock()
            self.__runout_thread = None
            self.__runout_event = None

            self.__filament_available = self.__input_device.value
            self.__input_device.when_activated = lambda: self._submit(self.__input_went_up)
            self.__input_device.when_deactivated = lambda: self._submit(self.__input_went_down)

        def start_checking(self):
            if self.__running:
                return
            self.__running = True
            self.__filament_available = self.__input_device.value
            if not self.__filament_available:
                self.__check_if_runout()
            self._log("Filament Sensor via interrupt started")

        def stop_checking(self):
            if not self.__running:
                return
            self.__stop_runout_checking()
            self.__running = False
            self._log("Filament Sensor via interrupt stopped")

        def __input_went_up(self):
            if self.__filament_available is True:
                return
            with self.__lock:
                self.__filament_available = True
                self.__stop_runout_checking()
            self._log("Filament became available")

        def __input_went_down(self):
            if self.__filament_available is False:
                return
            with self.__lock:
                self.__filament_available = False
                self.__check_if_runout()
            self._log("Filament became unavailable")

        def __check_if_runout(self):
            if not self.__running:
                return
            self.__runout_thread = Thread(target=self.__runout_checker)
            self.__runout_event = Event()
            self.__runout_thread.start()

        def __runout_checker(self):
            self.__runout_event.wait(self.__runout_time)
            if not self.__runout_event.is_set():
                self._runout()
                self._log("Run out time passed, printer paused")
                return
            self._log("Filament has returned")

        def __stop_runout_checking(self):
            if self.__runout_event is not None:
                self.__runout_event.set()
                self.__runout_event = None
                self.__runout_thread.join()
                self.__runout_thread = None

        def is_currently_available(self):
            return self.__filament_available

        def close(self):
            self.stop_checking()
            self.__input_device.close()
            self._close_pool()
            self._log("Closed interrupt")

    def get_assets(self):
        return {
            "js": ["js/filamentbuddy.js"],
            "css": ["css/filamentbuddy.css"]
        }

    def get_update_information(self):
        return {
            "filamentbuddy": {
                "displayName": "Filamentbuddy Plugin",
                "displayVersion": self._plugin_version,
                "type": "github_release",
                "user": "danieleborgo",
                "repo": "OctoPrint-FilamentBuddy",
                "current": self._plugin_version,
                "pip": "https://github.com/danieleborgo/OctoPrint-FilamentBuddy/archive/{target_version}.zip",
            }
        }


# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "FilamentBuddy Plugin"

# Set the Python version your plugin is compatible with below. Recommended is Python 3 only for all new plugins.
# OctoPrint 1.4.0 - 1.7.x run under both Python 3 and the end-of-life Python 2.
# OctoPrint 1.8.0 onwards only supports Python 3.
__plugin_pythoncompat__ = ">=3,<4"  # Only Python 3


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = FilamentBuddyPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
