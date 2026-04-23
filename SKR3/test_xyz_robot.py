# test_xyz_robot.py

from xyz_robot import XYZRobot

robot = XYZRobot(port="COM5", baudrate=115200, timeout=2.0)

try:
    robot.connect()
    print("Verbunden:", robot.is_connected)

    robot.move_relative(dx=-185, dy=-100, feedrate=5000)



finally:
    robot.disconnect()
    print("Verbindung geschlossen")
