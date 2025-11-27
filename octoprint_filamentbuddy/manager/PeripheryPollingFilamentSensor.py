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

from periphery import GPIO

from .AbstractPollingFilamentSensorManager import AbstractPollingFilamentSensorManager
from .support import GPIONotFoundException


class PeripheryPollingFilamentSensor(AbstractPollingFilamentSensorManager):
    def __init__(self, logger, runout_f, pin: int, polling_time: int, runout_time: int, empty_v: str, invert_pull: bool):
        super().__init__(logger, runout_f, polling_time, runout_time, empty_v, invert_pull)
        try:
            self.__input_device = GPIO(
                "/dev/gpiochip0",
                pin,
                "in",
                bias="pull_up" if self._is_empty_high ^ self._invert_pull else "pull_down"
            )
        except ImportError:
            raise GPIONotFoundException()

        self._log("Periphery polling successfully initialized")

    def is_currently_available(self):
        return self.__input_device.read() ^ self._is_empty_high

    def _close_sensor(self):
        self.__input_device.close()