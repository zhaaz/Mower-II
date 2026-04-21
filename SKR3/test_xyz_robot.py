# test_xyz_robot.py

from xyz_robot import XYZRobot

robot = XYZRobot(port="COM5", baudrate=115200, timeout=2.0)

try:
    robot.connect()
    print("Verbunden:", robot.is_connected)


    responses = robot.move_relative(x=-100, y=150, z = 0, feedrate=6000)


finally:
    robot.disconnect()
    print("Verbindung geschlossen")
