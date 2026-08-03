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

import os

# GPIO character devices are exposed as /dev/gpiochip0, /dev/gpiochip1, ...
GPIOCHIP_PATH_TEMPLATE = "/dev/gpiochip{}"
GPIOCHIP_PROBE_COUNT = 8


class GPIONotFoundException(ImportError):
    def __init__(self):
        super().__init__("Impossible to import the GPIO manager module")


class LibraryTestResult:
    """
    Outcome of a backend self-test. It is intentionally serializable so the plugin can
    forward it to the settings UI as-is, where the message explains to the user whether
    the selected sensor backend works and, if not, why.
    """

    def __init__(self, available: bool, message: str):
        self.available = available
        self.message = message

    def to_dict(self) -> dict:
        return {"available": self.available, "message": self.message}


def is_gpio_available() -> bool:
    # Modern GPIO char devices
    for i in range(GPIOCHIP_PROBE_COUNT):
        if os.path.exists(GPIOCHIP_PATH_TEMPLATE.format(i)):
            return True

    # Old sysfs GPIO interface
    if os.path.isdir("/sys/class/gpio"):
        entries = os.listdir("/sys/class/gpio")
        if any(name.startswith("gpio") for name in entries):
            return True
        if "export" in entries and "unexport" in entries:
            return True

    return False
