import os


class GPIONotFoundException(ImportError):
    def __init__(self):
        super().__init__("Impossible to import the GPIO manager module")


def is_gpio_available() -> bool:
    # Modern GPIO char devices
    for i in range(8):
        if os.path.exists(f"/dev/gpiochip{i}"):
            return True

    # Old sysfs GPIO interface
    if os.path.isdir("/sys/class/gpio"):
        entries = os.listdir("/sys/class/gpio")
        if any(name.startswith("gpio") for name in entries):
            return True
        if "export" in entries and "unexport" in entries:
            return True

    return False
