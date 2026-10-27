import unittest

from agentpet import sprites as s


class ClawdTest(unittest.TestCase):
    def test_front_pose_matches_claude_codes_sprite(self):
        self.assertEqual(s.clawd(), (
            "...#############..",
            "...#############..",
            "...##k#######k##..",
            "...##k#######k##..",
            ".#################",
            ".#################",
            "...#############..",
            "...#############..",
            "...#.#.......#.#..",
            "...#.#.......#.#..",
        ))

    def test_closed_eyes_are_a_dark_line_at_the_bottom_of_the_eye_cell(self):
        g = s.clawd("closed")
        self.assertEqual(g[3], "...#kk######kk##..")
        self.assertEqual(g[2], "...#############..")

    def test_looking_moves_the_eyes_to_the_top_row(self):
        self.assertEqual(s.clawd("left")[0], "...#k#######k###..")
        self.assertEqual(s.clawd("right")[0], "...###k#######k#..")

    def test_lifted_feet(self):
        self.assertEqual(s.clawd(feet="left")[8], "...#.#............")
        self.assertEqual(s.clawd(feet="right")[8], ".............#.#..")

    def test_every_pose_and_turn_frame_has_the_same_size(self):
        poses = [s.clawd(e, a, f) for e in s.EYES for a in s.ARMS for f in s.FEET]
        poses += [s.clawd_turn(n) for n in s.SPIN]
        for g in poses:
            self.assertEqual(len(g), s.CLAWD_H)
            self.assertTrue(all(len(r) == s.CLAWD_W for r in g))

    def test_spin_starts_and_ends_facing_front(self):
        self.assertEqual(s.clawd_turn(s.SPIN[0]), s.clawd())
        self.assertEqual(s.clawd_turn(s.SPIN[-1]), s.clawd())
        self.assertEqual(s.clawd_turn("~back"), s.mirror(s.clawd_turn("back")))

    def test_no_eyes_seen_from_behind(self):
        self.assertNotIn("k", "".join(s.clawd_turn("back")))

    def test_quarter_turns(self):
        g = s.clawd("left", "one-up")
        self.assertEqual(s.rotate(g, 1)[0], "".join(row[0] for row in reversed(g)))     # clockwise
        self.assertEqual((len(s.rotate(g, 1)), len(s.rotate(g, 1)[0])), (s.CLAWD_W, s.CLAWD_H))
        self.assertEqual(s.rotate(g, 2), s.mirror(s.flip(g)))
        self.assertEqual(s.rotate(g, -1), s.rotate(g, 3))
        self.assertEqual(s.rotate(g, 4), g)


class HermesTest(unittest.TestCase):
    def test_drawing_rows_are_the_full_width(self):
        for rows in (s._HEAD, s._BODY):
            self.assertTrue(all(len(r) == s.HERMES_W for r in rows))

    def test_every_variant_has_the_same_size_and_known_colours(self):
        for kw in ({}, {"eyes": "open"}, {"arm": "up"}, {"arm": "wave"}, {"arm": "down"}, {"legs": "left"},
                   {"legs": "right", "back_arm": 1}, {"bow": 1}, {"glow": True, "orb_dy": -1}, {"with_orb": False}):
            g = s.hermes(**kw)
            self.assertEqual(len(g), s.HERMES_H, kw)
            self.assertTrue(all(len(r) == s.HERMES_W for r in g), kw)
            self.assertTrue(set("".join(g)) <= set(s.PALETTE) | {"."}, kw)

    def test_mirror_twice_is_the_same(self):
        g = s.hermes(arm="wave")
        self.assertEqual(s.mirror(s.mirror(g)), g)
        self.assertNotEqual(s.mirror(g), g)

    def test_she_stands_on_the_ground(self):
        self.assertNotEqual(set(s.hermes()[-1]), {"."})
        self.assertEqual(set(s.hermes(legs="left")[-1]) - {"."}, {"B"})


class EffectsTest(unittest.TestCase):
    def test_confetti_is_deterministic_and_falls(self):
        self.assertEqual(s.confetti(0.5, 18), s.confetti(0.5, 18))
        early = sum(y for _, y, _ in s.confetti(0.4, 18))
        late = sum(y for _, y, _ in s.confetti(2.0, 18))
        self.assertGreater(late, early)


if __name__ == "__main__":
    unittest.main()
