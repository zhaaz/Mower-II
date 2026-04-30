# test_xyz_robot.py

from xyz_robot import XYZRobot

robot = XYZRobot(port="COM5", baudrate=115200, timeout=2.0)

try:
    robot.connect()
    print("Verbunden:", robot.is_connected)

    #robot.homing()
    robot.mark_text("P.1053", x=200.0, y=280.0, height=5.0)



finally:
    robot.disconnect()
    print("Verbindung geschlossen")
