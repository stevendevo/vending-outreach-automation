import unittest
from policy import minimums


class PolicyTest(unittest.TestCase):
    def test_near_is_600_simple_menu(self):
        for town in ["Bryn Mawr, PA", "Cherry Hill, NJ", "Horsham, PA", "Mount Laurel, NJ", "King of Prussia, PA", "Souderton, PA"]:
            self.assertEqual(minimums(town)["simple_menu"], 600, town)

    def test_far_is_750_everywhere(self):
        for town in ["Union, NJ", "Somerset, NJ", "Princeton, NJ"]:
            m = minimums(town)
            self.assertEqual((m["simple_menu"], m["full_menu"]), (750, 750), town)

    def test_full_menu_stays_750_nearby(self):
        self.assertEqual(minimums("Bryn Mawr, PA")["full_menu"], 750)

    def test_towns_near_the_line_are_held(self):
        for town in ["New Castle, DE", "Wilmington, DE", "Souderton, PA"]:
            m = minimums(town)
            if m["borderline"]:
                self.assertIsNone(m["simple_menu"], town)
        self.assertTrue(minimums("New Castle, DE")["borderline"])

    def test_unknown_town_never_guesses(self):
        with self.assertRaises(KeyError):
            minimums("Atlantis, NJ")


if __name__ == "__main__":
    unittest.main()
