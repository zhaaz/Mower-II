# demo_device.py

import time


class DemoDevice:
    def __init__(self):
        self.connected = False
        self.value = 0

    def connect(self):
        time.sleep(1.0)
        self.connected = True

    def disconnect(self):
        time.sleep(0.5)
        self.connected = False

    def reset(self):
        if not self.connected:
            raise RuntimeError("Gerät ist nicht verbunden.")

        time.sleep(0.5)
        self.value = 0

    def do_slow_work(self):
        if not self.connected:
            raise RuntimeError("Gerät ist nicht verbunden.")

        time.sleep(2.0)
        self.value += 1
        return self.value

    def get_value(self):
        if not self.connected:
            raise RuntimeError("Gerät ist nicht verbunden.")

        return self.value