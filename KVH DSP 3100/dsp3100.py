import serial
import threading
import time

LSB_TO_DEG = 2.384e-8
PRINT_INTERVAL = 1.0  # Nur für Testzwecke


class DSP3100:
    def __init__(self):
        self.ser = None
        self.thread = None
        self.running = False

        self.angle = 0.0
        self.valid_packets = 0
        self.skipped_bytes = 0
        self.lock = threading.Lock()

        self.drift = 0.0  # °/s
        self.sampling_rate = 1024  # Hz (wenn du das weißt)

        self._drift_active = False
        self._drift_sum = 0.0
        self._drift_count = 0
        self._drift_start = 0.0
        self._drift_duration = 0.0

    def connect(self, port, baudrate=375000):
        try:
            self.ser = serial.Serial(
                port,
                baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_ODD,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            print(f"✅ Verbunden mit {port} @ {baudrate} Baud.")
            self.running = True
            self.thread = threading.Thread(target=self._read_loop, daemon=True)
            self.thread.start()
        except serial.SerialException as e:
            print(f"❌ Verbindungsfehler: {e}")
            self.ser = None

    def disconnect(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join()
        if self.ser and self.ser.is_open:
            self.ser.close()
            print("🔌 Verbindung geschlossen.")
        self.ser = None

    def _read_loop(self):
        buffer = bytearray()
        skipped = 0
        last_print = time.time()

        while self.running:
            b = self.ser.read(1)
            if len(b) == 0:
                continue

            buffer += b

            while len(buffer) >= 5:
                block = buffer[:5]
                checksum = (~sum(block[0:4])) & 0xFF
                status_ok = (block[3] & 0x01) == 0

                if block[4] == checksum and status_ok:
                    angle_change = self._decode_angle(block)

                    # Falls Driftmessung aktiv ist
                    if self._drift_active:
                        now = time.time()
                        self._drift_sum += angle_change  # nicht korrigiert!
                        self._drift_count += 1

                        if now - self._drift_start >= self._drift_duration:
                            duration = now - self._drift_start
                            if duration > 0 and self._drift_count > 0:
                                with self.lock:
                                    self.drift = self._drift_sum / duration
                                print(f"✅ Drift abgeschlossen: {self.drift:.10f} °/s aus {self._drift_count} Messungen")
                            else:
                                print("⚠️ Driftmessung fehlgeschlagen.")
                            self._drift_active = False

                    # Driftkompensation anwenden
                    drift_correction = self.drift / self.sampling_rate
                    corrected_change = angle_change - drift_correction

                    with self.lock:
                        self.angle += corrected_change
                        self.valid_packets += 1
                        self.skipped_bytes += skipped
                    skipped = 0
                    buffer = buffer[5:]
                else:
                    buffer = buffer[1:]
                    skipped += 1
                    self.skipped_bytes += 1

            now = time.time()
            if now - last_print >= 1.0:  # einmal pro Sekunde
                with self.lock:
                    print(f"🧭 Aktueller Winkel: {self.angle:+.6f}°")
                last_print = now

    def _decode_angle(self, packet):
        raw = int.from_bytes(packet[0:3][::-1], byteorder='little', signed=True)
        return raw * LSB_TO_DEG * -2

    def get_angle(self):
        with self.lock:
            return self.angle

    def get_drift(self):
        with self.lock:
            return self.drift

    def reset_angle(self):
        with self.lock:
            self.angle = 0.0

    def determine_drift(self, sekunden):
        with self.lock:
            self._drift_sum = 0.0
            self._drift_count = 0
            self._drift_duration = sekunden
            self._drift_start = time.time()
            self._drift_active = True
            self.drift = 0.0  # Vorherige Drift zurücksetzen
        print(f"⚙️ Starte Driftmessung über {sekunden} Sekunden...")

