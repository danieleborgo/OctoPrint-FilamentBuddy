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

from abc import ABC, abstractmethod
from concurrent.futures.thread import ThreadPoolExecutor

from .support import GPIONotFoundException, LibraryTestResult


class GenericFilamentSensorManager(ABC):
    """
    This class, as the name suggest, represents in an abstract way a filament sensor.
    Its purpose is to let the main plugin abstract on how it is effectively implemented,
    so it can handle multiple sensors without any modifications. Consequently, the
    plugin uses only the public methods here defined that the extender has to implement.
    """

    def __init__(self, logger, runout_f):
        """
        The constructor requires just two essential parameters, since the filament sensor
        specific ones are taken directly by the extender. This because these could be very
        different from one sensor to another.
        :param logger: an instance of OctoPrint logger
        :param runout_f: this is the action to perform when the filament is over
        """
        self.__pool = ThreadPoolExecutor(max_workers=1)
        self.__logger = logger
        self.__runout_f = runout_f

    @classmethod
    def test_backend(cls, logger, *args, **kwargs) -> LibraryTestResult:
        """
        Fully verify that this backend works on the running system, instead of merely
        checking that a library can be imported. It builds a real instance (which imports
        the library and opens the GPIO line), performs an actual read and then releases
        everything. Any failure is reported through a human-readable message, whose detail
        is delegated to the polymorphic ``_unavailable_reason`` so each backend can explain
        its own requirements.
        :param logger: an instance of OctoPrint logger
        :param args: the backend-specific constructor arguments (pin, times, ...)
        :param kwargs: the backend-specific keyword constructor arguments (e.g. gpiochip)
        :return: a LibraryTestResult describing the outcome
        """
        try:
            manager = cls(logger, lambda: None, *args, **kwargs)
        except GPIONotFoundException:
            return LibraryTestResult(False, cls._unavailable_reason())

        try:
            manager.is_currently_available()
        except Exception as e:
            return LibraryTestResult(False, f"The backend loaded but reading the sensor failed: {e}")
        finally:
            manager.close()

        return LibraryTestResult(True, "The library works and the sensor pin was read successfully.")

    @classmethod
    def _unavailable_reason(cls) -> str:
        """
        Explain why this backend is not usable on the running system. Subclasses override
        it to point at their specific missing requirement (library, version, hardware).
        """
        return "The required GPIO library is not available on this system."

    @abstractmethod
    def start_checking(self) -> None:
        """
        This method has to be invoked when the filament sensing has to start. Consequently,
        the extender has to define here what is needed to do to launch the sensing process.
        """
        pass

    @abstractmethod
    def stop_checking(self) -> None:
        """
        This is the previous method opposite, since it stops the filament sensing. The
        extender has to consider all the possible outcome cases like, as instance, a
        run out or the filament never missing.
        """
        pass

    @abstractmethod
    def is_currently_available(self) -> bool:
        """
        This is a method that returns the current filament state.
        :return: true if the filament is available, otherwise false
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        This is the method to invoke when this instance becomes no more useful, so it closes
        what the constructor opened, calls stop_checking and _close_pool. After this, the
        instance becomes dead and cannot be used again if not instantiated newly.
        """
        pass

    def _submit(self, to_run) -> None:
        """
        This class has a ThreadPool to run code that may be too heavy to be executed in
        callbacks. This method is the way to use it.
        :param to_run: the action to run in the ThreadPool
        """
        self.__pool.submit(to_run)

    def _close_pool(self) -> None:
        """
        This method closes the ThreaPool and must be invoked in the close method implementation.
        """
        self.__pool.shutdown(wait=False)

    def _log(self, message: str) -> None:
        """
        In the case the extender has to log something in OctoPrint, it can use this method.
        :param message: the string to log
        """
        self.__logger.info(message)

    def _runout(self) -> None:
        """
        This is the method to invoke when the extender find out the filament has run out.
        """
        self.__runout_f()
