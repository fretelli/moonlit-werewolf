"""Offline rule tests, not evidence of hardware functionality."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from werewolf_engine import Game, Role, RuleError


def game():
    result = Game()
    for seat, role in enumerate([Role.WOLF, Role.WOLF, Role.SEER,
                                 Role.VILLAGER, Role.VILLAGER, Role.VILLAGER], 1):
        result.register(seat, role)
    result.start()
    return result


def night(g, target, inspection=1):
    g.choose_wolf_target(target)
    g.finish_wolf_window()
    if g.seer_alive():
        g.inspect(inspection)
    g.finish_seer_window()


def speeches(g):
    while g.phase == "day_speech":
        g.finish_speech(g.speaker)


def ballots(g, choices):
    for choice in choices:
        g.vote(g.voter, choice)
    return g.resolve_votes()


class RulesTests(unittest.TestCase):
    def test_registration_constraints(self):
        g = Game()
        for seat in [0, 7, True, "1"]:
            with self.assertRaises(RuleError):
                g.register(seat, Role.WOLF)
        g.register(1, Role.WOLF)
        with self.assertRaises(RuleError):
            g.register(1, Role.WOLF)
        g.register(2, Role.WOLF)
        with self.assertRaises(RuleError):
            g.register(3, Role.WOLF)
        with self.assertRaises(RuleError):
            g.start()

    def test_no_implicit_night_action(self):
        g = game()
        with self.assertRaises(RuleError):
            g.finish_wolf_window()
        with self.assertRaises(RuleError):
            g.choose_wolf_target(1)
        g.choose_wolf_target(3)
        with self.assertRaises(RuleError):
            g.choose_wolf_target(4)
        g.finish_wolf_window()
        with self.assertRaises(RuleError):
            g.finish_seer_window()
        self.assertTrue(g.inspect(1))
        g.finish_seer_window()
        self.assertNotIn(3, g.alive)
        self.assertEqual(g.phase, "day_speech")

    def test_good_win_complete_two_rounds(self):
        g = game()
        night(g, 4)
        speeches(g)
        self.assertEqual(ballots(g, [1] * 5), 1)
        self.assertEqual(g.phase, "day_result")
        g.next_night()
        night(g, 5, inspection=2)
        speeches(g)
        ballots(g, [2] * 3)
        self.assertEqual(g.winner, "good")
        self.assertEqual(g.phase, "finished")
        with self.assertRaises(RuleError):
            g.next_night()

    def test_wolf_parity_win(self):
        g = game()
        night(g, 4)
        speeches(g)
        ballots(g, [5] * 5)
        self.assertEqual(g.winner, "wolves")

    def test_dead_seer_dummy_window(self):
        g = game()
        night(g, 3)
        speeches(g)
        ballots(g, [1] * 5)
        g.next_night()
        g.choose_wolf_target(4)
        g.finish_wolf_window()
        self.assertEqual(g.phase, "night_seer")
        self.assertFalse(g.seer_alive())
        self.assertEqual(g.seer_targets(), set())
        with self.assertRaises(RuleError):
            g.inspect(2)
        g.finish_seer_window()
        self.assertEqual(g.phase, "day_speech")

    def test_runoff_then_tie_no_elimination(self):
        g = game()
        night(g, 4)
        speeches(g)
        ballots(g, [1, 1, 2, 2, None])
        self.assertTrue(g.runoff)
        self.assertEqual(g.vote_targets(), {1, 2})
        with self.assertRaises(RuleError):
            g.vote(g.voter, 3)
        ballots(g, [1, 1, 2, 2, None])
        self.assertEqual(g.phase, "day_result")
        self.assertIsNone(g.last_eliminated)
        self.assertEqual(len(g.alive), 5)

    def test_all_abstain_and_invalid_sequence(self):
        g = game()
        with self.assertRaises(RuleError):
            g.vote(1, 2)
        night(g, 4)
        with self.assertRaises(RuleError):
            g.finish_speech(2)
        speeches(g)
        with self.assertRaises(RuleError):
            g.vote(2, 1)
        with self.assertRaises(RuleError):
            g.resolve_votes()
        ballots(g, [None] * 5)
        self.assertEqual(g.phase, "day_result")
        self.assertFalse(g.runoff)
        self.assertIsNone(g.last_eliminated)

    def test_private_actions_do_not_change_public_state(self):
        g = game()
        before = g.public_state()
        g.choose_wolf_target(4)
        self.assertEqual(before, g.public_state())
        g.finish_wolf_window()
        before = g.public_state()
        g.inspect(1)
        self.assertEqual(before, g.public_state())
        g.finish_seer_window()
        speeches(g)
        g.vote(1, 2)
        public = g.public_state()
        self.assertEqual(public["tally"], {})
        self.assertNotIn("roles", public)
        self.assertNotIn("votes", public)
        public["alive"].clear()
        self.assertEqual(len(g.alive), 5)
        g.abort()
        self.assertFalse(g._roles)
        self.assertFalse(g._votes)
        self.assertEqual(g.phase, "aborted")


if __name__ == "__main__":
    unittest.main()
