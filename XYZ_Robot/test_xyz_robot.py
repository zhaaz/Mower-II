# test_xyz_robot.py
from setuptools.command.build_ext import have_rtld

from xyz_robot import XYZRobot

robot = XYZRobot(port="COM5", baudrate=115200, timeout=2.0)

try:
    robot.connect()
    print("Verbunden:", robot.is_connected)

    robot.homing()
    # robot.move_absolute(250,200, feedrate=6000)

    robot.homing()



finally:
    robot.disconnect()
    print("Verbindung geschlossen")
