import unittest

from tests import _stubs  # noqa: F401 - stubs for libraries missing here
from core.capture import physical_region


class PhysicalRegionTest(unittest.TestCase):
    def test_no_scaling_is_unchanged(self):
        self.assertEqual(physical_region(100, 50, 300, 200),
                         {"left": 100, "top": 50, "width": 300, "height": 200})

    def test_second_monitor_on_the_left(self):
        # Monitor at x = -1920; coordinates are global, nothing is shifted.
        self.assertEqual(physical_region(-1500, 10, 200, 100, (-1920, 0), 1.0),
                         {"left": -1500, "top": 10, "width": 200, "height": 100})

    def test_scaled_monitor(self):
        # 150 % scaling on a monitor that starts at x = 1920: the corner stays,
        # distances inside the monitor grow.
        self.assertEqual(physical_region(2020, 100, 200, 100, (1920, 0), 1.5),
                         {"left": 2070, "top": 150, "width": 300, "height": 150})

    def test_never_empty(self):
        self.assertEqual(physical_region(0, 0, 0, 0)["width"], 1)


if __name__ == "__main__":
    unittest.main()
