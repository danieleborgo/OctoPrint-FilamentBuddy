"""
FilamentBuddy OctoPrint plugin
Copyright (C) 2023-2026 Daniele Borgo
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

from .AbstractPollingFilamentSensorManager import AbstractPollingFilamentSensorManager
from .support import GPIONotFoundException


class PeripheryPollingFilamentSensor(AbstractPollingFilamentSensorManager):
    def __init__(self, logger, runout_f, pin: int, polling_time: int, runout_time: int, empty_v: str, invert_pull: bool):
        super().__init__(logger, runout_f, polling_time, runout_time, empty_v, invert_pull)
        try:
            from periphery import GPIO
            self.__input_device = GPIO(
                "/dev/gpiochip0",
                pin,
                "in",
                bias="pull_up" if self._is_empty_high ^ self._invert_pull else "pull_down"
            )
        except (ImportError, OSError):
            raise GPIONotFoundException()

        self._log("Periphery polling successfully initialized")

    @classmethod
    def _unavailable_reason(cls):
        try:
            import periphery  # noqa: F401
        except ImportError:
            return ("The 'python-periphery' library is not installed. It is only installed on "
                    "Linux systems.")
        return ("python-periphery is installed but the GPIO could not be opened. Check the pin "
                "number and that /dev/gpiochip0 exists and is accessible.")

    def is_currently_available(self):
        return bool(self.__input_device.read() ^ self._is_empty_high)

    def _close_sensor(self):
        self.__input_device.close()