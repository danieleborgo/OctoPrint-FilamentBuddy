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

from enum import Enum
from flask import jsonify
from paho.mqtt import client as mqtt

import octoprint.plugin
from octoprint.events import Events
from octoprint_filamentbuddy import GenericFilamentSensorManager
from octoprint_filamentbuddy.manager import is_gpio_available
from octoprint_filamentbuddy.manager.PollingFilamentSensorManager import PollingFilamentSensorManager
from octoprint_filamentbuddy.manager.InterruptFilamentSensorManager import InterruptFilamentSensorManager

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

    REMOVING_TARGET_MIN_T = 5  # °C

    def __init__(self):
        super().__init__()
        self.__is_gpio_available = is_gpio_available()
        self.__fs_manager = None
        self.__fr_state = FilamentBuddyPlugin.FRState.INACTIVE

    def on_after_startup(self):
        self.__reset_plugin()
        self._logger.info("Plugin ready")

    def on_shutdown(self):
        if self.__fs_manager is not None:
            self.__fs_manager.close()

    def __reset_plugin(self):
        self.__initialize_filament_sensor()
        self.__initialize_filament_remover()

    def __initialize_filament_sensor(self):
        if self.__fs_manager is not None:
            self.__fs_manager.close()
        self.__fs_manager = None
        if not self.__is_gpio_available or not self.__get_bool("fs", "en"):
            return

        if "polling".__eq__(self.__get_string("fs", "sensor_mode")):
            self.__fs_manager = PollingFilamentSensorManager(
                self._logger,
                self.__runout_action,
                self.__get_int("fs", "sensor_pin"),
                self.__get_int("fs", "polling_time"),
                self.__get_int("fs", "run_out_time"),
                self.__get_string("fs", "empty_voltage")
            )
            self.__enable_if_printing()
            return

        if "interrupt".__eq__(self.__get_string("fs", "sensor_mode")):
            self.__fs_manager = InterruptFilamentSensorManager(
                self._logger,
                self.__runout_action,
                self.__get_int("fs", "sensor_pin"),
                self.__get_int("fs", "run_out_time"),
                self.__get_string("fs", "empty_voltage")
            )
            self.__enable_if_printing()
            return

        raise Exception("Implementation error: this FS type is unknown")

    def __runout_action(self):
        if self.__get_bool("fs", "use_pause"):
            self._printer.pause_print()
        self._printer.commands(
            [c.strip() for c in self.__get_string("fs", "run_out_command").split("\n")]
        )
        self.__send_notification("The filament has run out", True)
        self.__send_mqtt_if_en()

    def __send_mqtt_if_en(self):
        if not self.__get_bool("fs", "mqtt_en"):
            return

        client_id = self.__get_string("fs", "mqtt_client_id")
        address = self.__get_string("fs", "mqtt_address")
        port = self.__get_int("fs", "mqtt_port")
        topic = self.__get_string("fs", "mqtt_topic")
        message = self.__get_string("fs", "mqtt_message_string").encode('utf-8')

        self._logger.info(f"Preparing to send MQTT message from {client_id} to {address}:{port}/{topic}")

        client = mqtt.Client(client_id)
        client.on_publish = lambda cl, userdata, mid: self._logger.info("MQTT message sent: " + str(message))

        if self.__get_bool("fs", "mqtt_use_login"):
            username = self.__get_string("fs", "mqtt_username")
            password = self.__get_string("fs", "mqtt_password")
            client.username_pw_set(username, password)

        try:
            client.connect(address, port)
            client.loop_start()
            info = client.publish(
                topic=topic,
                payload=message,
                qos=0,
            )
            info.wait_for_publish()
            client.disconnect()
        except ConnectionRefusedError:
            self._logger.info("Impossible to connect to MQTT broker")
            self.__send_notification("Impossible to connect to MQTT broker")

    def __enable_if_printing(self):
        if self._printer.is_printing():
            self.__fs_manager.start_checking()

    def __initialize_filament_remover(self):
        if (self.__get_bool("fr", "en")
                and "temperature" == self.__get_string("fr", "hook_mode")
                and (self._printer.is_printing() or self._printer.is_pausing() or self._printer.is_paused())):
            self.__fr_state = FilamentBuddyPlugin.FRState.WAIT_FOR_REMOVING
            return
        self.__fr_state = FilamentBuddyPlugin.FRState.INACTIVE

    def on_event(self, event, payload):
        if not event.startswith("Print"):
            return

        if Events.PRINT_STARTED.__eq__(event):
            if self.__fs_manager is not None:
                self.__fs_manager.start_checking()
                if not self.__fs_manager.is_currently_available():
                    self.__send_notification("Filament not found, starting run out timeout")
            if self.__get_bool("fr", "en"):
                if "outside" == self.__get_string("fr", "hook_mode"):
                    self.__insert_filament()
                else:
                    self.__fr_state = FilamentBuddyPlugin.FRState.WAIT_FOR_INSERTING
            return

        if Events.PRINT_PAUSED.__eq__(event):
            if self.__fs_manager is not None:
                self.__fs_manager.stop_checking()
            return

        if Events.PRINT_RESUMED.__eq__(event):
            if self.__fs_manager is not None:
                self.__fs_manager.start_checking()
                if not self.__fs_manager.is_currently_available():
                    self.__send_notification("Filament not found, starting run out timeout")
            return

        if event in (Events.PRINT_DONE, Events.PRINT_FAILED):
            if self.__fs_manager is not None:
                self.__fs_manager.stop_checking()
            if self.__get_bool("fr", "en"):
                if "outside" == self.__get_string("fr", "hook_mode"):
                    self.__remove_filament()
                else:
                    if self.__fr_state == FilamentBuddyPlugin.FRState.WAIT_FOR_REMOVING:
                        self.__remove_filament()
                    self.__initialize_filament_remover()
            return

    def on_temperature_received(self, comm_instance, parsed_temperatures, *args, **kwargs):
        if (self.__fr_state == FilamentBuddyPlugin.FRState.INACTIVE or
                not self._printer.is_printing() or
                'T0' not in parsed_temperatures or
                not isinstance(parsed_temperatures['T0'], tuple) or
                len(parsed_temperatures['T0']) != 2 or
                parsed_temperatures['T0'][1] is None):
            return parsed_temperatures

        current_t, target_t = parsed_temperatures['T0']
        # self._logger.info(f"Tc: {current_t}°C, Tt: {target_t}°C, {self.__fr_state}")

        if self.__fr_state == FilamentBuddyPlugin.FRState.WAIT_FOR_INSERTING:
            if current_t > self.__get_int("fr", "min_needed_temp"):
                self.__insert_filament()
                self.__fr_state = FilamentBuddyPlugin.FRState.WAIT_FOR_REMOVING
        else:
            # Necessarily WAIT_FOR_REMOVAL
            if target_t < FilamentBuddyPlugin.REMOVING_TARGET_MIN_T:
                self.__remove_filament()
                self.__fr_state = FilamentBuddyPlugin.FRState.INACTIVE

        return parsed_temperatures

    def __generate_fr_command(self, length, command):
        if "simplified".__eq__(self.__get_string("fr", "command_mode")):
            c = ["G91", f"G1 E{length}", "G90"]
            if self.__get_bool("fr", "force_cold"):
                c.insert(0, "M302 P1")
            return c
        return [c.strip() for c in command.split("\n")]

    def __remove_filament(self):
        length = self.__get_int("fr", "retract_length")
        if length <= 0:
            return
        commands = self.__generate_fr_command(
            -length,
            self.__get_string("fr", "retract_command")
        )
        self._printer.commands(commands)
        self._logger.info(f"Removing filament with: {commands}")

    def __insert_filament(self):
        length = self.__get_int("fr", "extrude_length")
        if length <= 0:
            return
        commands = self.__generate_fr_command(
            length,
            self.__get_string("fr", "extrude_command")
        )
        self._printer.commands(commands)
        self._logger.info(f"Inserting filament with: {commands}")

    def get_api_commands(self):
        return dict(
            filament_status=[],
            test_mqtt=[]
        )

    def on_api_command(self, command, data):
        if command == "filament_status":
            return jsonify({
                'state': self.__fs_manager is not None,
                'filament': None if self.__fs_manager is None else self.__fs_manager.is_currently_available()
            })

        if command == "test_mqtt":
            self.__send_mqtt_if_en()
            return jsonify({})

        self._logger.info("API request unknown: " + command)
        return None

    def __send_notification(self, message: str, is_severe: bool = False):
        self._plugin_manager.send_plugin_message("filamentbuddy", {"message": message, "is_severe": is_severe})

    def __get_raw_value(self, source: Literal["fc", "fs", "fr"], param):
        modified = self._settings.get([source])
        if param in modified:
            return modified[param]
        return FilamentBuddyPlugin.DEFAULT_SETTINGS[source][param]

    def __get_int(self, source: Literal["fc", "fs", "fr"], param: str) -> int:
        return int(self.__get_raw_value(source, param))

    def __get_float(self, source: Literal["fc", "fs", "fr"], param: str) -> float:
        return float(self.__get_raw_value(source, param))

    def __get_bool(self, source: Literal["fc", "fs", "fr"], param: str) -> bool:
        return bool(self.__get_raw_value(source, param))

    def __get_string(self, source: Literal["fc", "fs", "fr"], param: str) -> str:
        return str(self.__get_raw_value(source, param))

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
            "toolbar_en": True,
            "mqtt_en": False,
            "mqtt_address": "",
            "mqtt_port": 1883,
            "mqtt_client_id": "OctoprintFilamentBuddy",
            "mqtt_use_login": False,
            "mqtt_username": "",
            "mqtt_password": "",
            "mqtt_topic": "FilamentBuddy",
            "mqtt_message_string": "Filament is over"
        },

        # Filament Remover
        "fr": {
            "en": False,
            "hook_mode": "outside",
            "min_needed_temp": 190,  # °C
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
                "is_gpio_available": self.__is_gpio_available,
                "default": FilamentBuddyPlugin.DEFAULT_SETTINGS
            }
        }

    def on_settings_save(self, data):
        data["is_gpio_available"] = self.__is_gpio_available
        data["default"] = FilamentBuddyPlugin.DEFAULT_SETTINGS
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self.__reset_plugin()

    class FRState(Enum):
        INACTIVE = 0,
        WAIT_FOR_INSERTING = 1,
        WAIT_FOR_REMOVING = 2

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
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
        "octoprint.comm.protocol.temperatures.received": __plugin_implementation__.on_temperature_received
    }
