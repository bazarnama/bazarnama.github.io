import importlib.util, pathlib, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("repair_history", ROOT / "tools" / "repair_history.py")
rh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rh)
H = 3600


class SpikeTests(unittest.TestCase):
    def test_isolated_v_shaped_spike_is_found(self):
        pts = [[0, 100.0], [H, 60.0], [2 * H, 100.5]]
        self.assertEqual(rh.find_spikes(pts, 10.0), [[H, 60.0]])

    def test_persistent_level_change_is_not_a_spike(self):
        pts = [[0, 100.0], [H, 60.0], [2 * H, 59.5], [3 * H, 60.2]]
        self.assertEqual(rh.find_spikes(pts, 10.0), [])

    def test_move_below_limit_is_kept(self):
        self.assertEqual(rh.find_spikes([[0, 100.0], [H, 95.0], [2 * H, 100.0]], 10.0), [])

    def test_gap_longer_than_six_hours_is_never_touched(self):
        self.assertEqual(rh.find_spikes([[0, 100.0], [10 * H, 60.0], [11 * H, 100.0]], 10.0), [])

    def test_ends_of_series_are_never_removed(self):
        self.assertEqual(rh.find_spikes([[0, 50.0], [H, 100.0], [2 * H, 100.0]], 10.0), [])


if __name__ == "__main__":
    unittest.main()
