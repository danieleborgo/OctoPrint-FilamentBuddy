"""
FilamentBuddy OctoPrint plugin
Copyright (C) 2025 Daniele Borgo
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

from re import fullmatch
import digitalio
import board
from .AbstractPollingFilamentSensorManager import AbstractPollingFilamentSensorManager
from .support import GPIONotFoundException


class BlinkaPollingFilamentSensor(AbstractPollingFilamentSensorManager):
    def __init__(self, logger, runout_f, pin: int, polling_time: int, runout_time: int, empty_v: str, invert_pull: bool):
        super().__init__(logger, runout_f, polling_time, runout_time, empty_v, invert_pull)

        pin_attr = f"D{pin}"
        try:
            if not hasattr(board, pin_attr):
                self._log(f"Pin not found: {pin_attr}")
                raise GPIONotFoundException()

            pin = getattr(board, pin_attr)

            self.__input_device = digitalio.DigitalInOut(pin)
            self.__input_device.direction = digitalio.Direction.INPUT
            self.__input_device.pull = digitalio.Pull.UP if self._is_empty_high ^ self._invert_pull else digitalio.Pull.DOWN

        except (AttributeError, ValueError, ImportError):
            raise GPIONotFoundException()

        self.__available_pins = [int(attr[1:]) for attr in dir(board) if fullmatch(r"D\d+", attr)]
        self._log("Blinka polling successfully initialized")

    def verify_if_pin_exists(self, pin: int) -> bool:
        return pin in self.__available_pins

    def get_bcm_pins_list(self):
        return self.__available_pins[:]

    def is_currently_available(self):
        return bool(self.__input_device.value) ^ self._is_empty_high

    def _close_sensor(self):
        try:
            self.__input_device.deinit()
        except Exception:
            pass
