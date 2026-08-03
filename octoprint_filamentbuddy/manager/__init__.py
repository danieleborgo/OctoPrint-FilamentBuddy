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

from .support import (
    is_gpio_available,
    GPIONotFoundException,
    LibraryTestResult,
    GPIOCHIP_PATH_TEMPLATE,
    GPIOCHIP_PROBE_COUNT,
)
from .AbstractPollingFilamentSensorManager import AbstractPollingFilamentSensorManager
from .PeripheryPollingFilamentSensor import PeripheryPollingFilamentSensor
from .BlinkaPollingFilamentSensorManager import BlinkaPollingFilamentSensor
from .LibgpiodPollingFilamentSensorManager import LibgpiodPollingFilamentSensor

DEVICE_TREE_MODEL_PATH = "/proc/device-tree/model"
RASPBERRY_PI_MARKER = "raspberry pi"


def is_raspberry_pi() -> bool:
    try:
        with open(DEVICE_TREE_MODEL_PATH) as f:
            return RASPBERRY_PI_MARKER in f.read().lower()
    except OSError:
        return False


def list_gpiochips():
    return [i for i in range(GPIOCHIP_PROBE_COUNT) if os.path.exists(GPIOCHIP_PATH_TEMPLATE.format(i))]


__all__ = [
    "is_gpio_available",
    "GPIONotFoundException",
    "LibraryTestResult",
    "AbstractPollingFilamentSensorManager",
    "PeripheryPollingFilamentSensor",
    "BlinkaPollingFilamentSensor",
    "LibgpiodPollingFilamentSensor",
    "is_raspberry_pi",
    "list_gpiochips"
]
