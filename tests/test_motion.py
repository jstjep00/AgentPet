"""Getting around: the floor, the walls, the top of the screen, falling, and the mouse."""

import random
import unittest

from agentpet import motion as m
from agentpet.motion import AIR, CEILING, FLOOR, HELD, LEFT, RIGHT, Area, Motion

AREA = Area(0, 30, 1200, 730)       # a top bar of 30 px
W, H = 72, 40


def run(mo, start, seconds, mode="roam", dt=0.04, seen=None):
    t = start
    while t < start + seconds:
        t += dt
        mo.step(t, dt, AREA, W, H, 40, mode)
        if seen is not None:
            seen.append((mo.surface, mo.x, mo.y))
    return t


def inside(test, x, y):
    reach = max(W, H) / 2 + 0.5
    test.assertTrue(AREA.left + reach - W <= x <= AREA.right - reach + W and AREA.top <= y <= AREA.bottom, (x, y))


class MotionTest(unittest.TestCase):
    def test_a_demo_climb_goes_up_the_wall_over_the_top_and_drops_on_its_head(self):
        mo = Motion(random.Random(4))
        mo.place(AREA, W, H, 600)
        mo.adventure(0)
        seen = []
        run(mo, 0, 120, seen=seen)
        surfaces = [s for s, _, _ in seen]
        order = [s for i, s in enumerate(surfaces) if i == 0 or surfaces[i - 1] != s]
        self.assertEqual(order[:5], [FLOOR, order[1], CEILING, AIR, FLOOR])
        self.assertIn(order[1], (LEFT, RIGHT))
        self.assertEqual(mo.landing[0], "bonk")
        for _, x, y in seen:
            inside(self, x, y)

    def test_where_it_sits_on_each_surface(self):
        self.assertEqual(Motion.centre(FLOOR, 500, AREA, W, H), (500, 730 - 20))
        self.assertEqual(Motion.centre(CEILING, 500, AREA, W, H), (500, 30 + 20))
        self.assertEqual(Motion.centre(LEFT, 300, AREA, W, H), (0 + 20, 300))     # on its side: H wide
        self.assertEqual(Motion.centre(RIGHT, 300, AREA, W, H), (1200 - 20, 300))
        self.assertEqual(Motion.limits(LEFT, AREA, W, H), (30 + 36, 730 - 36))

    def test_mostly_on_the_floor_but_it_gets_around(self):
        mo = Motion(random.Random(11))
        mo.place(AREA, W, H)
        seen = []
        run(mo, 0, 1800, seen=seen, dt=0.1)
        share = {s: sum(1 for x in seen if x[0] == s) / len(seen) for s in (FLOOR, LEFT, RIGHT, CEILING, AIR)}
        self.assertGreater(share[FLOOR], 0.5)
        self.assertGreater(share[LEFT] + share[RIGHT] + share[CEILING], 0.03)
        for _, x, y in seen:
            inside(self, x, y)

    def test_called_down_it_hops_down_and_lands_on_its_feet(self):
        mo = Motion(random.Random(1))
        mo.place(AREA, W, H)
        mo._go(CEILING, 400, AREA, W, H)
        t = run(mo, 0, 0.1, mode="ground")
        self.assertEqual(mo.surface, AIR)
        run(mo, t, 2, mode="ground")
        self.assertEqual(mo.surface, FLOOR)
        self.assertEqual(mo.landing[0], "land")
        x = mo.x
        run(mo, 10, 3, mode="ground")
        self.assertEqual(mo.x, x)

    def test_picked_up_and_dropped_mid_air_it_falls(self):
        mo = Motion(random.Random(1))
        mo.place(AREA, W, H, 600)
        mo.pick_up()
        self.assertEqual(mo.surface, HELD)
        mo.hold_at(600, 100)
        run(mo, 0, 1)
        self.assertEqual((mo.x, mo.y), (600, 100))                    # held: it stays in your hand
        mo.drop(1, AREA, W, H)
        self.assertEqual(mo.surface, AIR)
        run(mo, 1, 2)
        self.assertEqual((mo.surface, mo.landing[0]), (FLOOR, "bonk"))   # a long way down
        self.assertEqual(mo.landed(mo.landing[1] + 0.1), "bonk")
        self.assertEqual(mo.landed(mo.landing[1] + 1.0), "dizzy")
        self.assertIsNone(mo.landed(mo.landing[1] + m.BONK_S + m.DIZZY_S + 0.1))

    def test_a_short_drop_lands_on_its_feet(self):
        mo = Motion(random.Random(1))
        mo.pick_up()
        mo.hold_at(600, 650)
        mo.drop(0, AREA, W, H)
        run(mo, 0, 1)
        self.assertEqual(mo.landing[0], "land")

    def test_dropped_at_an_edge_it_holds_on(self):
        for x, y, surface in ((25, 400, LEFT), (1180, 300, RIGHT), (600, 55, CEILING), (600, 715, FLOOR)):
            mo = Motion(random.Random(1))
            mo.pick_up()
            mo.hold_at(x, y)
            mo.drop(0, AREA, W, H)
            self.assertEqual(mo.surface, surface, (x, y))
            inside(self, mo.x, mo.y)

    def test_faces_the_way_it_goes_on_every_surface(self):
        # on the left wall its right points down; on the right wall, up
        for surface, start, target, facing in ((FLOOR, 300, 500, 1), (FLOOR, 500, 300, -1), (LEFT, 600, 200, -1),
                                               (RIGHT, 600, 200, 1), (CEILING, 300, 500, 1)):
            mo = Motion(random.Random(1))
            mo._go(surface, start, AREA, W, H)
            mo.target = target
            mo.step(0, 0.1, AREA, W, H, 40)
            self.assertEqual(mo.facing, facing, surface)


if __name__ == "__main__":
    unittest.main()
