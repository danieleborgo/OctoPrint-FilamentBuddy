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

from threading import Lock, Thread, Event

try:
    from gpiozero import DigitalInputDevice
except ModuleNotFoundError:
    from octoprint_filamentbuddy.manager import DigitalInputDeviceForOlderPy as DigitalInputDevice

from octoprint_filamentbuddy.manager import GPIONotFoundException
from octoprint_filamentbuddy.GenericFilamentSensorManager import GenericFilamentSensorManager


class InterruptFilamentSensorManager(GenericFilamentSensorManager):
    BOUNCE_TIME = 0.02  # s

    def __init__(self, logger, runout_f, pin: int, runout_time: int, empty_v: str):
        super().__init__(logger, runout_f)

        self.__pin = pin
        self.__runout_time = runout_time
        self.__is_empty_high = "high".__eq__(empty_v.lower())

        try:
            self.__input_device = DigitalInputDevice(
                pin=pin,
                pull_up=self.__is_empty_high,
                bounce_time=InterruptFilamentSensorManager.BOUNCE_TIME
            )
        except ImportError:
            raise GPIONotFoundException()

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
        if self.__runout_event is not None and not self.__runout_event.is_set():
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
