# test_xyz_robot.py

from xyz_robot import XYZRobot

robot = XYZRobot(port="COM5", baudrate=115200, timeout=2.0)

try:
    robot.connect()
    print("Verbunden:", robot.is_connected)

    #robot.homing_z()
    robot.mark_plus(100,100, 40)



finally:
    robot.disconnect()
    print("Verbindung geschlossen")
