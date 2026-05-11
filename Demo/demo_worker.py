# demo_worker.py

import threading
import queue
from demo_device import DemoDevice


class DemoWorker:
    def __init__(self, on_log=None, on_status=None, on_value=None, on_error=None):
        self.device = DemoDevice()

        self.command_queue = queue.Queue()
        self.running = False
        self.thread = None

        self.on_log = on_log
        self.on_status = on_status
        self.on_value = on_value
        self.on_error = on_error

    def start(self):
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

        self._log("Worker gestartet")

    def stop(self):
        self.running = False
        self.command_queue.put(("stop", None))

    def send_command(self, command: str, data=None):
        self.command_queue.put((command, data))

    def _run(self):
        while self.running:
            command, data = self.command_queue.get()

            try:
                if command == "stop":
                    break

                elif command == "connect":
                    self._status("Verbinden...")
                    self.device.connect()
                    self._status("Verbunden")
                    self._log("Gerät verbunden")

                elif command == "disconnect":
                    self.device.disconnect()
                    self._status("Nicht verbunden")
                    self._log("Gerät getrennt")

                elif command == "reset":
                    self.device.reset()
                    self._value(self.device.get_value())
                    self._log("Wert zurückgesetzt")

                elif command == "slow_work":
                    self._status("Beschäftigt...")
                    value = self.device.do_slow_work()
                    self._value(value)
                    self._status("Verbunden")
                    self._log(f"Arbeit abgeschlossen. Wert={value}")

            except Exception as e:
                self._error(str(e))
                self._status("Fehler")

    def _log(self, text):
        if self.on_log:
            self.on_log(text)

    def _status(self, text):
        if self.on_status:
            self.on_status(text)

    def _value(self, value):
        if self.on_value:
            self.on_value(value)

    def _error(self, text):
        if self.on_error:
            self.on_error(text)