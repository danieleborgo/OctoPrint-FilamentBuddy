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

from typing import Callable

try:
    from RPi import GPIO
    is_imported = True
except RuntimeError:
    is_imported = False


class GPIONotFoundException(ImportError):
    def __init__(self):
        super().__init__("Impossible to import the GPIO manager module")


def is_gpio_available() -> bool:
    try:
        from gpiozero import pi_info
        pi_info()
        # gpiozero is perfectly working on this Raspberry
        return True
    except ModuleNotFoundError:
        # gpiozero is not supported, so the decision is delegated to RPi.GPIO
        return is_imported
    except ImportError:
        # gpiozero is working but no GPIO scheme has been found
        return False


"""
Some OctoPrint users still use out of life Python versions and some of these 
are no more compatible with the newest gpiozero version (2.0). In these cases, 
this last module throws an exception named ModuleNotFoundError. To solve this 
there are two ways: update Python to a newer version, like 3.11, or Downgrade 
gpiozero to the last working version, 1.6.2. The first solution is preferable, 
because of the support, but not all the users want or can follow this way. 
The other option is the gpiozero downgrade, which can be performed via pip: 
    pip install gpiozero==1.6.2 
Nevertheless, this solution has a major issue, which is related to the fact 
that other plugins may require a newer gpiozero version. Consequently, if the 
module version is downgraded, it may cause unwanted behavior or errors in these 
plugins that, obviously, doesn't consider this case. Hence, this downgrade, 
despite being here explained, is highly discouraged, even if it works in most 
cases. The first option, so upgrading Python, remains the most suggested one. 

Nevertheless, there is another solution simpler than the first one and with 
no risks compared to the second, that is avoiding to use gpiozero in favour of 
RPi.GPIO. This last is the module on which gpiozero is based, that, apparently, 
with the current version 0.7.1, doesn't have incompatibilities with the previous 
version. On the other hand, it offers a more limited set of less encapsulated 
features. This is the purpose of the following class, a dummy object that offers 
a restricted set of features needed by FilamentBuddy and that mimics the one 
currently used by the plugin, which is gpiozero DigitalInputDevice, but 
implemented via RPi.GPIO. This class is the only way for who cannot update their 
Python version and FilamentBuddy is able to automatically detect when to use it, 
so no further user configuration is required. 
The obvious and immediate question is: why not using directly RPI.GPIO module 
instead of gpiozero? There is no a universally true answer, so some developers 
would have preferred to just convert the entire plugin to RPi.GPIO and to avoid 
completely this class. This would have been surely more uniform but RPi.GPIO 
doesn't offer object as encapsulated as gpiozero and this is the reason why 
the module has not been switched. For instance, via gpiozero it is enough to 
import DigitalInputDevice and, via its methods and properties, it is possible 
to delegate to this class the reading and the edges detection while in the other 
module requires to write a little bit more code, as shown later in this file. 
This is the reason followed here but, as explained before, other users may 
prefer other approaches.
"""


class DigitalInputDeviceForOlderPy:

    @property
    def value(self):
        provisional = False if GPIO.input(self.__pin) == 0 else True
        return not provisional if self.__pull_up else provisional

    @property
    def when_activated(self):
        return self.__when_activated

    @property
    def when_deactivated(self):
        return self.__when_deactivated

    @when_activated.setter
    def when_activated(self, value: Callable):
        self.__when_activated = value

    @when_deactivated.setter
    def when_deactivated(self, value: Callable):
        self.__when_deactivated = value

    def __init__(self, pin: int, pull_up: bool, bounce_time=1):
        if not is_imported:
            raise GPIONotFoundException()

        self.__pin = pin
        self.__pull_up = pull_up
        self.__when_activated = None
        self.__when_deactivated = None

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(
            self.__pin, GPIO.IN,
            pull_up_down=GPIO.PUD_UP if self.__pull_up else GPIO.PUD_DOWN
        )
        GPIO.add_event_detect(
            self.__pin, GPIO.BOTH, callback=self.__process_edge, bouncetime=bounce_time)

    def __process_edge(self, pin):
        if self.__pin != pin:
            return

        if self.value:
            if self.__when_activated is not None:
                self.when_activated()
        else:
            if self.__when_deactivated is not None:
                self.when_deactivated()

    def close(self):
        GPIO.remove_event_detect(self.__pin)
