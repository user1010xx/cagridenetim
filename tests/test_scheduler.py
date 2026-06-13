import unittest

from bot.scheduler import _should_wait_before_next_department


class SchedulerTest(unittest.TestCase):
    def test_waits_between_departments_but_not_after_last_department(self) -> None:
        self.assertTrue(_should_wait_before_next_department(0, 3))
        self.assertTrue(_should_wait_before_next_department(1, 3))
        self.assertFalse(_should_wait_before_next_department(2, 3))

    def test_single_department_does_not_wait(self) -> None:
        self.assertFalse(_should_wait_before_next_department(0, 1))


if __name__ == "__main__":
    unittest.main()