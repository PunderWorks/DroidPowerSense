"""Unit tests for soa.py. Run: python3 -m unittest discover -s scripts/spice"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from soa import (CSD18532_SOA_30V, cumulative_energy, derate, fmt_window, max_window_power, soa_limit,
                 soa_margin)


def rect_pulse(power, width, total=0.1, step=1e-5):
    """A rectangular power pulse of `width` seconds starting at t = 0, sampled every `step`."""
    n = int(round(total / step))
    t = [i * step for i in range(n + 1)]
    p = [power if ti < width - 1e-12 else 0.0 for ti in t]
    return t, p


class SoaLimitTest(unittest.TestCase):
    def test_chart_points_are_returned_exactly(self):
        for duration, power in CSD18532_SOA_30V:
            self.assertAlmostEqual(soa_limit(duration), power)

    def test_interpolates_log_log_between_points(self):
        # Halfway (in log time) between 1 ms (291 W) and 10 ms (122 W) is the geometric mean.
        self.assertAlmostEqual(soa_limit(10 ** -2.5), (291.0 * 122.0) ** 0.5, places=6)

    def test_clamps_outside_the_chart(self):
        self.assertEqual(soa_limit(1e-9), CSD18532_SOA_30V[0][1])
        self.assertEqual(soa_limit(100.0), CSD18532_SOA_30V[-1][1])

    def test_derate(self):
        self.assertAlmostEqual(derate(25.0), 1.0)
        self.assertAlmostEqual(derate(60.0), 0.72)
        self.assertEqual(derate(150.0), 0.0)


class WindowPowerTest(unittest.TestCase):
    def test_cumulative_energy_of_constant_power(self):
        energy = cumulative_energy([0.0, 1.0, 2.0], [5.0, 5.0, 5.0])
        self.assertEqual(energy, [0.0, 5.0, 10.0])

    def test_rectangular_pulse_average_equals_its_power_inside_the_pulse(self):
        t, p = rect_pulse(100.0, 5e-3)
        self.assertAlmostEqual(max_window_power(t, p, 1e-3), 100.0, delta=1.0)

    def test_window_longer_than_pulse_averages_down(self):
        t, p = rect_pulse(100.0, 5e-3)
        # 0.5 J spread over a 10 ms window.
        self.assertAlmostEqual(max_window_power(t, p, 10e-3), 50.0, delta=1.0)


class SoaMarginTest(unittest.TestCase):
    def test_pulse_inside_soa_passes(self):
        # 50 W for 5 ms is well under the derated 10 ms (88 W) and 1 ms (210 W) limits.
        t, p = rect_pulse(50.0, 5e-3)
        ratio, *_ = soa_margin(t, p)
        self.assertLess(ratio, 1.0)

    def test_pulse_outside_soa_fails_and_names_the_window(self):
        # 500 W for 5 ms: over the 1 ms limit (~210 W derated) by about 2.4x.
        t, p = rect_pulse(500.0, 5e-3)
        ratio, window, avg, limit = soa_margin(t, p)
        self.assertGreater(ratio, 1.0)
        self.assertAlmostEqual(avg / limit, ratio)
        self.assertIn(window, (1e-3, 3e-3))

    def test_fmt_window(self):
        self.assertEqual(fmt_window(10e-6), "10us")
        self.assertEqual(fmt_window(3e-3), "3ms")
        self.assertEqual(fmt_window(1.0), "1s")


if __name__ == "__main__":
    unittest.main()
