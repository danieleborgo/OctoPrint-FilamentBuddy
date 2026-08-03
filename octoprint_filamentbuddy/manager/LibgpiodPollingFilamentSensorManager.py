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
from .support import GPIONotFoundException, GPIOCHIP_PATH_TEMPLATE


class LibgpiodPollingFilamentSensor(AbstractPollingFilamentSensorManager):
    CONSUMER = "FilamentBuddy"

    def __init__(self, logger, runout_f, pin: int, polling_time: int, runout_time: int, empty_v: str,
                 invert_pull: bool, gpiochip: int = 0):
        super().__init__(logger, runout_f, polling_time, runout_time, empty_v, invert_pull)

        try:
            import gpiod
            from gpiod.line import Direction, Bias, Value

            # libgpiod v1 exposes a completely different API (gpiod.Chip / chip.get_line) and
            # has no request_lines: treat it as unsupported instead of crashing later.
            if not hasattr(gpiod, "request_lines"):
                self._log("Installed gpiod is < 2.0; the libgpiod backend requires gpiod >= 2.0")
                raise GPIONotFoundException()

            self.__offset = pin
            self.__value_active = Value.ACTIVE

            settings = gpiod.LineSettings(
                direction=Direction.INPUT,
                bias=Bias.PULL_UP if self._is_empty_high ^ self._invert_pull else Bias.PULL_DOWN
            )
            self.__request = gpiod.request_lines(
                GPIOCHIP_PATH_TEMPLATE.format(gpiochip),
                consumer=self.CONSUMER,
                config={pin: settings}
            )

        except GPIONotFoundException:
            raise
        except (ImportError, AttributeError, OSError):
            raise GPIONotFoundException()

        self._log("libgpiod polling successfully initialized")

    @classmethod
    def _unavailable_reason(cls):
        import sys
        if sys.version_info < (3, 9):
            return (f"The libgpiod backend needs Python 3.9 or newer, but OctoPrint is running on "
                    f"Python {sys.version_info[0]}.{sys.version_info[1]}, so the 'gpiod' "
                    f"library was not installed.")
        try:
            import gpiod
        except ImportError:
            return "The 'gpiod' library is not installed on this system."
        if not hasattr(gpiod, "request_lines"):
            return "The installed 'gpiod' is older than 2.0; this backend requires gpiod >= 2.0."
        return ("gpiod >= 2.0 is installed but the GPIO line could not be requested. Check the "
                "GPIO chip, the line offset and that you have permission to access it.")

    def is_currently_available(self):
        raw = 1 if self.__request.get_value(self.__offset) == self.__value_active else 0
        return bool(raw ^ self._is_empty_high)

    def _close_sensor(self):
        try:
            self.__request.release()
        except OSError as e:
            self._log(f"Failed to release GPIO: {e}")
