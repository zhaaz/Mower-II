# test_xyz_robot.py

from xyz_robot import XYZRobot

robot = XYZRobot(port="COM5", baudrate=115200, timeout=2.0)

try:
    robot.connect()
    print("Verbunden:", robot.is_connected)

    #robot.homing()
    robot.mark_point_with_label(
        x=250.0,
        y=200.0,
        label="Z-764",
        marker_size=10.0,
        marker_shape="plus",
        text_height=8.0,
        angle_deg=45.0
    )



finally:
    robot.disconnect()
    print("Verbindung geschlossen")
