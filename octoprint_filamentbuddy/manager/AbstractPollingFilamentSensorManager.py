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
from abc import abstractmethod
from threading import Event

from .GenericFilamentSensorManager import GenericFilamentSensorManager


class AbstractPollingFilamentSensorManager(GenericFilamentSensorManager):
    BOUNCE_TIME = 1  # ms
    VERIFYING_TIME = 1  # s

    def __init__(self, logger, runout_f, polling_time: int, runout_time: int, empty_v: str, invert_pull: bool):
        super().__init__(logger, runout_f)
        self.__polling_time = polling_time
        self.__runout_time = runout_time
        self._is_empty_high = "high".__eq__(empty_v.lower())
        self._invert_pull = invert_pull
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
                self.__event.wait(AbstractPollingFilamentSensorManager.VERIFYING_TIME)
                self._log("First missing filament")
                while self.__verifying:
                    if self.is_currently_available():
                        # the filament came back before the deadline
                        self.__verifying = False
                        self._log("Filament has returned")
                        continue
                    if count * AbstractPollingFilamentSensorManager.VERIFYING_TIME >= self.__runout_time:
                        self._log("Run out time passed, printer paused")
                        self._runout()
                        self.stop_checking()
                        return
                    count += 1
                    self.__event.wait(AbstractPollingFilamentSensorManager.VERIFYING_TIME)


    def close(self):
        if self.__running:
            self.stop_checking()
        self._close_sensor()
        self._close_pool()
        self._log("Closed polling")

    @abstractmethod
    def _close_sensor(self):
        pass