import unittest
from unittest.mock import patch

from tools.native_30m_resources import ComputeBudget, StageObserver, active_budget, observed_call, current_rss_bytes


class ComputeBudgetTests(unittest.TestCase):
    def test_window_dimension_precedes_cells(self):
        with self.assertRaisesRegex(ValueError, 'budget_window_dimension'):
            ComputeBudget(max_window_nodes=9, max_window_cells=1).check_window([{}], [10, 10], 1)
        with self.assertRaisesRegex(ValueError, 'budget_window_cells'):
            ComputeBudget(max_window_cells=1).check_window([{}], [9, 9], 1)

    def test_pages_bucket_nodes_intervals(self):
        with self.assertRaisesRegex(ValueError, 'budget_pages'):
            ComputeBudget(max_pages=1).check_window([{}, {}], [9, 9], 1)
        with self.assertRaisesRegex(ValueError, 'budget_rainfall_entries'):
            ComputeBudget().check_catchment(100001, 1)
        with self.assertRaisesRegex(ValueError, 'budget_rainfall_entries'):
            ComputeBudget().check_catchment(20000, 72)
        with self.assertRaisesRegex(ValueError, 'budget_channel_nodes'):
            ComputeBudget().check_nodes(129)
        with self.assertRaisesRegex(ValueError, 'budget_coupled_intervals'):
            ComputeBudget().check_window([{}], [9, 9], 13)

    def test_byte_budgets_before_large_arrays(self):
        with self.assertRaisesRegex(ValueError, 'budget_local_q_bytes'):
            ComputeBudget(max_local_q_bytes=1).check_catchment(10, 72)
        with self.assertRaisesRegex(ValueError, 'budget_trace_reservation'):
            ComputeBudget(max_trace_reserved_bytes=1).check_window([{}], [9, 9], 1)
        self.assertEqual(ComputeBudget().check_trace_reservation(12), 3*1024**3)

    def test_invalid_budget_not_silently_cast(self):
        for kwargs in ({'max_pages': True}, {'max_seconds': float('nan')}, {'max_rss_bytes': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, 'invalid_budget'):
                ComputeBudget(**kwargs).validate()


class StageObserverTests(unittest.TestCase):
    def test_current_rss_available(self):
        self.assertGreater(current_rss_bytes(), 0)

    def test_phase_peak_is_not_lifetime_peak(self):
        sample = [100]
        with patch('tools.native_30m_resources.current_rss_bytes', side_effect=lambda: sample[0]):
            with StageObserver(ComputeBudget(max_rss_bytes=1000), period_seconds=60) as observer:
                with observer.stage('prefix'):
                    sample[0] = 500
                sample[0] = 50
                observed_call('reach', lambda: None)
            report = observer.record()
        self.assertEqual(report['stages']['prefix']['max_sampled_current_rss_bytes'], 500)
        self.assertEqual(report['stages']['reach']['max_sampled_current_rss_bytes'], 50)
        self.assertEqual(report['stages']['reach']['samples'], 2)
        self.assertIs(report['sampling_can_miss_between_sample_spikes'], True)
        self.assertIs(report['is_os_memory_quota'], False)

    def test_limit_callback_without_killing_unit_test(self):
        failures = []
        with patch('tools.native_30m_resources.current_rss_bytes', return_value=11):
            with self.assertRaisesRegex(ValueError, 'budget_rss'):
                with StageObserver(ComputeBudget(max_rss_bytes=10), on_limit=failures.append):
                    self.fail('must reject before entering observed work')
        self.assertEqual(failures[0]['reason'], 'budget_rss')

    def test_observer_context_restored_after_failure(self):
        original = active_budget()
        with patch('tools.native_30m_resources.current_rss_bytes', return_value=100):
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                with StageObserver(ComputeBudget(), period_seconds=60):
                    observed_call('failure', lambda: (_ for _ in ()).throw(RuntimeError('injected')))
        self.assertIs(active_budget(), original)

    def test_measurement_failure_is_not_reported_as_zero_rss(self):
        with patch('tools.native_30m_resources.current_rss_bytes', side_effect=OSError('unavailable')):
            with self.assertRaisesRegex(OSError, 'unavailable'):
                with StageObserver(ComputeBudget()):
                    pass


if __name__ == '__main__':
    unittest.main()
