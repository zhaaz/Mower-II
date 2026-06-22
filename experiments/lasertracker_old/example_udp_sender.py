import socket
import time

UDP_IP = "127.0.0.1"
UDP_PORT = 5005

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

counter = 0
while True:
    message = f"Hallo UDP {counter}"
    sock.sendto(message.encode(), (UDP_IP, UDP_PORT))
    print(f"Gesendet: {message}")
    counter += 1
    time.sleep(1)
