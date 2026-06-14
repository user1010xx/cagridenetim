import unittest
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from bot.models import DepartmentRules, Personnel
from bot.rules import CallRecord, PersonnelEvaluation, evaluate_department, normalize_calls
from bot.service import _filter_notified_violations, _violation_keys


TZ = ZoneInfo("Europe/Istanbul")


def dt(value: str) -> datetime:
    parts = [int(part) for part in value.split(":")]
    hour, minute = parts[:2]
    second = parts[2] if len(parts) > 2 else 0
    return datetime(2026, 6, 9, hour, minute, second, tzinfo=TZ)


def call(name: str, value: str, duration: int = 60, extension: str | None = None) -> CallRecord:
    return CallRecord(name, extension, dt(value), duration, "1")


class RulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = DepartmentRules(
            department_id=1,
            work_start_time=time(11, 10),
            pre_break_leave_time=None,
            break_start_time=time(13, 50),
            break_end_time=time(15, 15),
            post_break_start_time=None,
            work_end_time=time(18, 50),
            max_call_gap_minutes=15,
        )
        self.report_date = date(2026, 6, 9)
        self.personnel = [Personnel(1, 1, "Ali", "1001", True)]

    def evaluate(self, calls: list[CallRecord], now: str = "19:00"):
        return evaluate_department(calls, self.personnel, self.rules, self.report_date, dt(now), TZ)[0]

    def test_first_call_late_is_violation(self) -> None:
        result = self.evaluate([call("Ali", "11:25", extension="1001"), call("Ali", "18:55", extension="1001")])
        self.assertTrue(any("Mesai başlangıcı" in violation for violation in result.violations))

    def test_first_call_same_minute_with_seconds_is_not_violation(self) -> None:
        result = self.evaluate([call("Ali", "11:10:59", extension="1001"), call("Ali", "18:55", extension="1001")])

        self.assertFalse(any("Mesai başlangıcı" in violation for violation in result.violations))

    def test_first_call_next_minute_is_violation(self) -> None:
        result = self.evaluate([call("Ali", "11:11:00", extension="1001"), call("Ali", "18:55", extension="1001")])

        self.assertTrue(any("Mesai başlangıcı" in violation for violation in result.violations))

    def test_gap_over_limit_is_violation(self) -> None:
        result = self.evaluate(
            [
                call("Ali", "11:05", duration=60, extension="1001"),
                call("Ali", "11:30", extension="1001"),
                call("Ali", "18:55", extension="1001"),
            ]
        )
        self.assertTrue(any("Çağrı arası" in violation for violation in result.violations))

    def test_break_interval_is_excluded_from_gap(self) -> None:
        result = self.evaluate(
            [
                call("Ali", "11:05", extension="1001"),
                call("Ali", "13:49", duration=60, extension="1001"),
                call("Ali", "15:16", extension="1001"),
                call("Ali", "18:55", extension="1001"),
            ]
        )
        break_gap_violations = [
            violation for violation in result.violations if "13:49 - 15:16" in violation
        ]
        self.assertEqual(break_gap_violations, [])

    def test_work_end_requires_call_after_end(self) -> None:
        result = self.evaluate([call("Ali", "11:05", extension="1001"), call("Ali", "18:48", extension="1001")])
        self.assertTrue(any("Mesai bitişi" in violation for violation in result.violations))

    def test_call_continuing_after_work_end_is_not_work_end_violation(self) -> None:
        result = self.evaluate([call("Ali", "11:05", extension="1001"), call("Ali", "18:49", duration=180, extension="1001")])
        self.assertFalse(any("Mesai bitişi" in violation for violation in result.violations))

    def test_current_idle_gap_is_violation(self) -> None:
        result = self.evaluate(
            [
                call("Ali", "11:05", extension="1001"),
                call("Ali", "12:00", extension="1001"),
                call("Ali", "18:55", extension="1001"),
            ],
            now="12:30",
        )
        self.assertTrue(any("Güncel bekleme" in violation for violation in result.violations))

    def test_personnel_without_calls_is_detected(self) -> None:
        result = self.evaluate([])
        self.assertTrue(any("çağrı yok" in violation for violation in result.violations))

    def test_blank_rule_is_not_applied(self) -> None:
        self.rules = DepartmentRules(
            department_id=1,
            work_start_time=None,
            pre_break_leave_time=None,
            break_start_time=None,
            break_end_time=None,
            post_break_start_time=None,
            work_end_time=None,
            max_call_gap_minutes=None,
        )
        result = self.evaluate([])
        self.assertEqual(result.violations, [])

    def test_post_break_start_violation(self) -> None:
        self.rules = DepartmentRules(
            department_id=1,
            work_start_time=None,
            pre_break_leave_time=None,
            break_start_time=time(14, 0),
            break_end_time=time(15, 0),
            post_break_start_time=time(15, 15),
            work_end_time=None,
            max_call_gap_minutes=None,
        )
        result = self.evaluate([call("Ali", "15:20", extension="1001")], now="15:30")
        self.assertTrue(any("Mola sonrası" in violation for violation in result.violations))

    def test_post_break_start_same_minute_with_seconds_is_not_violation(self) -> None:
        self.rules = DepartmentRules(
            department_id=1,
            work_start_time=None,
            pre_break_leave_time=None,
            break_start_time=time(14, 0),
            break_end_time=time(15, 0),
            post_break_start_time=time(15, 15),
            work_end_time=None,
            max_call_gap_minutes=None,
        )

        result = self.evaluate([call("Ali", "15:15:59", extension="1001")], now="15:30")

        self.assertFalse(any("Mola sonrası" in violation for violation in result.violations))

    def test_post_break_start_next_minute_is_violation(self) -> None:
        self.rules = DepartmentRules(
            department_id=1,
            work_start_time=None,
            pre_break_leave_time=None,
            break_start_time=time(14, 0),
            break_end_time=time(15, 0),
            post_break_start_time=time(15, 15),
            work_end_time=None,
            max_call_gap_minutes=None,
        )

        result = self.evaluate([call("Ali", "15:16:00", extension="1001")], now="15:30")

        self.assertTrue(any("Mola sonrası" in violation for violation in result.violations))

    def test_pre_break_leave_violation(self) -> None:
        self.rules = DepartmentRules(
            department_id=1,
            work_start_time=None,
            pre_break_leave_time=time(13, 50),
            break_start_time=time(14, 0),
            break_end_time=time(15, 0),
            post_break_start_time=None,
            work_end_time=None,
            max_call_gap_minutes=None,
        )
        result = self.evaluate([call("Ali", "13:30", extension="1001")], now="14:00")
        self.assertTrue(any("Mola öncesi" in violation for violation in result.violations))

    def test_pre_break_leave_no_violation_when_call_reaches_limit(self) -> None:
        self.rules = DepartmentRules(
            department_id=1,
            work_start_time=None,
            pre_break_leave_time=time(13, 50),
            break_start_time=time(14, 0),
            break_end_time=time(15, 0),
            post_break_start_time=None,
            work_end_time=None,
            max_call_gap_minutes=None,
        )
        result = self.evaluate([call("Ali", "13:49", duration=120, extension="1001")], now="14:00")
        self.assertFalse(any("Mola öncesi" in violation for violation in result.violations))

    def test_pre_work_call_outside_start_window_then_call_before_work_start_is_not_violation(self) -> None:
        result = self.evaluate([call("Ali", "10:10", extension="1001"), call("Ali", "11:08", extension="1001")])

        self.assertFalse(any("Çağrı arası" in violation for violation in result.violations))

    def test_pre_work_call_outside_start_window_then_call_after_work_start_is_violation(self) -> None:
        result = self.evaluate([call("Ali", "10:10", extension="1001"), call("Ali", "11:11", extension="1001")])

        self.assertTrue(any("Çağrı arası" in violation for violation in result.violations))

    def test_pre_work_call_near_work_start_then_call_at_work_start_is_not_violation(self) -> None:
        result = self.evaluate([call("Ali", "10:58", extension="1001"), call("Ali", "11:10", extension="1001")])

        self.assertFalse(any("Çağrı arası" in violation for violation in result.violations))

    def test_pre_work_call_near_work_start_then_late_call_is_violation(self) -> None:
        result = self.evaluate([call("Ali", "10:58", extension="1001"), call("Ali", "11:14", extension="1001")])

        self.assertTrue(any("Çağrı arası" in violation for violation in result.violations))

    def test_pre_break_free_window_is_excluded_from_gap(self) -> None:
        self.rules = DepartmentRules(
            department_id=1,
            work_start_time=None,
            pre_break_leave_time=time(13, 50),
            break_start_time=time(14, 0),
            break_end_time=time(15, 0),
            post_break_start_time=time(15, 15),
            work_end_time=None,
            max_call_gap_minutes=15,
        )
        result = self.evaluate(
            [
                call("Ali", "13:49", duration=120, extension="1001"),
                call("Ali", "15:14", extension="1001"),
                call("Ali", "15:20", extension="1001"),
            ],
            now="15:30",
        )
        self.assertFalse(any("Çağrı arası" in violation for violation in result.violations))

    def test_post_break_free_window_only_applies_to_first_post_break_call(self) -> None:
        self.rules = DepartmentRules(
            department_id=1,
            work_start_time=None,
            pre_break_leave_time=time(13, 50),
            break_start_time=time(14, 0),
            break_end_time=time(15, 0),
            post_break_start_time=time(15, 15),
            work_end_time=None,
            max_call_gap_minutes=15,
        )
        result = self.evaluate(
            [
                call("Ali", "15:14", extension="1001"),
                call("Ali", "15:31", extension="1001"),
            ],
            now="15:40",
        )
        self.assertTrue(any("Çağrı arası" in violation for violation in result.violations))

    def test_personnel_on_weekly_leave_is_reported_as_leave(self) -> None:
        result = evaluate_department(
            [],
            self.personnel,
            self.rules,
            self.report_date,
            dt("19:00"),
            TZ,
            weekly_leave_names={"ali"},
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_on_leave)
        self.assertEqual(result[0].violations, [])

    def test_calls_during_leave_period_are_not_evaluated(self) -> None:
        result = evaluate_department(
            [call("Ali", "11:20", extension="1001"), call("Ali", "18:55", extension="1001")],
            self.personnel,
            self.rules,
            self.report_date,
            dt("19:00"),
            TZ,
            leave_periods={"ali": [(dt("11:00"), dt("19:00"))]},
        )[0]
        self.assertEqual(result.violations, [])
        self.assertTrue(result.is_on_leave)

    def test_total_call_count_keeps_calls_filtered_by_leave(self) -> None:
        result = evaluate_department(
            [call("Ali", "11:20", extension="1001"), call("Ali", "18:55", extension="1001")],
            self.personnel,
            self.rules,
            self.report_date,
            dt("19:00"),
            TZ,
            leave_periods={"ali": [(dt("11:00"), dt("19:00"))]},
        )[0]

        self.assertEqual(len(result.calls), 0)
        self.assertEqual(result.total_call_count, 2)
        self.assertTrue(result.is_on_leave)

    def test_total_call_duration_uses_talk_duration_when_available(self) -> None:
        result = evaluate_department(
            [
                CallRecord("Ali", "1001", dt("11:20"), 25, "1", talk_duration_seconds=5),
                CallRecord("Ali", "1001", dt("11:30"), 30, "1", talk_duration_seconds=7),
            ],
            self.personnel,
            self.rules,
            self.report_date,
            dt("11:40"),
            TZ,
        )[0]

        self.assertEqual(result.total_call_count, 2)
        self.assertEqual(result.total_call_duration_seconds, 12)

    def test_normalize_calls_accepts_invekto_grid_fields(self) -> None:
        records = normalize_calls(
            [
                {
                    "ARAMA TARİHİ": "10/06/2026",
                    "ARAMA SAATİ": "11:45:40",
                    "KONUŞMA SÜRESİ": "00:00:00",
                    "ÇALDIRMA SÜRESİ": "00:00:11",
                    "DAHİLİ ADI": "Ali -O",
                }
            ],
            TZ,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].extension_name, "Ali")
        self.assertEqual(records[0].duration_seconds, 11)

    def test_normalize_calls_prefers_talk_duration_over_ring_duration(self) -> None:
        records = normalize_calls(
            [
                {
                    "Date": "2026-06-09",
                    "Time": "11:45:40",
                    "CallTimeSecond": "5",
                    "RingTimeSecond": "20",
                    "ExtensionName": "Ali",
                }
            ],
            TZ,
        )

        self.assertEqual(records[0].duration_seconds, 5)

    def test_normalize_calls_keeps_talk_duration_separate_from_total_call_time(self) -> None:
        records = normalize_calls(
            [
                {
                    "Date": "2026-06-09",
                    "Time": "11:45:40",
                    "CallTimeSecond": "25",
                    "KONUŞMA SÜRESİ": "00:00:05",
                    "ExtensionName": "Ali",
                }
            ],
            TZ,
        )

        self.assertEqual(records[0].duration_seconds, 25)
        self.assertEqual(records[0].talk_duration_seconds, 5)

    def test_normalize_calls_keeps_call_when_only_talk_duration_exists(self) -> None:
        records = normalize_calls(
            [
                {
                    "Date": "2026-06-09",
                    "Time": "11:45:40",
                    "KONUŞMA SÜRESİ": "00:00:05",
                    "ExtensionName": "Ali",
                }
            ],
            TZ,
        )

        self.assertEqual(records[0].duration_seconds, 5)
        self.assertEqual(records[0].talk_duration_seconds, 5)

    def test_normalize_calls_accepts_minute_second_duration(self) -> None:
        records = normalize_calls(
            [
                {
                    "Date": "2026-06-09",
                    "Time": "11:45:40",
                    "CallTimeSecond": "01:05",
                    "ExtensionName": "Ali",
                }
            ],
            TZ,
        )

        self.assertEqual(records[0].duration_seconds, 65)

    def test_normalize_calls_accepts_combined_datetime_and_duration_fields(self) -> None:
        records = normalize_calls(
            [
                {
                    "CallDateTime": "2026-06-09T11:45:40",
                    "Duration": "00:00:05",
                    "ExtensionName": "Ali",
                }
            ],
            TZ,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].started_at.hour, 11)
        self.assertEqual(records[0].started_at.minute, 45)
        self.assertEqual(records[0].started_at.second, 40)
        self.assertEqual(records[0].duration_seconds, 5)

    def test_normalize_calls_accepts_separate_call_start_fields(self) -> None:
        records = normalize_calls(
            [
                {
                    "CallStartDate": "2026-06-09",
                    "CallStartTime": "11:45:40",
                    "Duration": "00:00:05",
                    "ExtensionName": "Ali",
                }
            ],
            TZ,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].started_at.hour, 11)
        self.assertEqual(records[0].started_at.minute, 45)
        self.assertEqual(records[0].started_at.second, 40)

    def test_normalize_calls_accepts_invekto_conversation_api_fields(self) -> None:
        records = normalize_calls(
            [
                {
                    "Direct": "1001",
                    "CreateDate": "2026-06-09",
                    "CreateTime": "11:45:40",
                    "RingTime": "00:00:03",
                    "WaitTime": "00:00:00",
                    "CallTime": "00:00:19",
                    "CallID": "call-1",
                    "IsCompleted": True,
                    "CompletedExtensionName": "Ali",
                }
            ],
            TZ,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].extension_name, "Ali")
        self.assertEqual(records[0].extension, "1001")
        self.assertEqual(records[0].duration_seconds, 19)
        self.assertEqual(records[0].started_at.hour, 11)
        self.assertEqual(records[0].started_at.minute, 45)

    def test_normalize_calls_derives_talk_duration_from_total_minus_ring_and_wait(self) -> None:
        records = normalize_calls(
            [
                {
                    "Direct": "1001",
                    "CreateDate": "2026-06-09",
                    "CreateTime": "11:45:40",
                    "RingTime": "00:00:08",
                    "WaitTime": "00:00:02",
                    "CallTime": "00:00:19",
                    "CompletedExtensionName": "Ali",
                }
            ],
            TZ,
        )

        self.assertEqual(records[0].duration_seconds, 19)
        self.assertEqual(records[0].talk_duration_seconds, 9)

    def test_normalize_calls_does_not_drop_unknown_event_type(self) -> None:
        records = normalize_calls(
            [
                {
                    "Date": "2026-06-09",
                    "Time": "11:45:40",
                    "CallTimeSecond": "5",
                    "ExtensionName": "Ali",
                    "EventType": "Conversation",
                }
            ],
            TZ,
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].event_type, "Conversation")

    def test_normalize_calls_does_not_use_extension_number_as_name(self) -> None:
        records = normalize_calls(
            [
                {
                    "Date": "2026-06-09",
                    "Time": "11:45:40",
                    "CallTimeSecond": "5",
                    "Extension": "1001",
                }
            ],
            TZ,
        )

        self.assertEqual(records[0].extension_name, "Bilinmeyen")
        self.assertEqual(records[0].extension, "1001")

    def test_normalize_calls_extracts_extension_from_name_parentheses(self) -> None:
        records = normalize_calls(
            [
                {
                    "Date": "2026-06-09",
                    "Time": "11:45:40",
                    "CallTimeSecond": "5",
                    "ExtensionName": "Alaz (310)",
                }
            ],
            TZ,
        )

        self.assertEqual(records[0].extension_name, "Alaz")
        self.assertEqual(records[0].extension, "310")

    def test_normalize_calls_extracts_three_digit_extension_from_name_without_parentheses(self) -> None:
        records = normalize_calls(
            [
                {
                    "Date": "2026-06-09",
                    "Time": "11:45:40",
                    "CallTimeSecond": "5",
                    "Name": "Alaz 310",
                }
            ],
            TZ,
        )

        self.assertEqual(records[0].extension, "310")

    def test_normalize_calls_does_not_extract_two_digit_date_part_as_extension(self) -> None:
        records = normalize_calls(
            [
                {
                    "Date": "2026-06-09",
                    "Time": "11:45:40",
                    "CallTimeSecond": "5",
                    "Name": "09.06.2026 Alaz 310",
                }
            ],
            TZ,
        )

        self.assertEqual(records[0].extension, "310")

    def test_normalize_calls_does_not_use_agent_name_as_extension(self) -> None:
        records = normalize_calls(
            [
                {
                    "Date": "2026-06-09",
                    "Time": "11:45:40",
                    "CallTimeSecond": "5",
                    "Agent": "Alaz 310",
                }
            ],
            TZ,
        )

        self.assertEqual(records[0].extension_name, "Alaz 310")
        self.assertEqual(records[0].extension, "310")

    def test_normalize_calls_accepts_alternative_extension_fields(self) -> None:
        records = normalize_calls(
            [
                {
                    "Date": "2026-06-09",
                    "Time": "11:45:40",
                    "CallTimeSecond": "5",
                    "AgentName": "Alaz",
                    "AgentExtension": "310",
                }
            ],
            TZ,
        )

        self.assertEqual(records[0].extension_name, "Alaz")
        self.assertEqual(records[0].extension, "310")

    def test_evaluate_department_ignores_api_people_outside_department_personnel(self) -> None:
        result = evaluate_department(
            [
                call("Ali", "11:10", extension="1001"),
                call("Veli", "11:30", extension="2001"),
            ],
            [Personnel(id=1, department_id=1, name="Ali", extension="1001", is_active=True)],
            self.rules,
            self.report_date,
            dt("11:40"),
            TZ,
        )

        self.assertEqual([evaluation.name for evaluation in result], ["Ali"])

    def test_evaluate_department_matches_numeric_extension_formats(self) -> None:
        result = evaluate_department(
            [call("Bilinmeyen", "11:30", extension="310.0")],
            [Personnel(id=1, department_id=1, name="Alaz", extension="310", is_active=True)],
            self.rules,
            self.report_date,
            dt("11:40"),
            TZ,
        )

        self.assertEqual(result[0].name, "Alaz")
        self.assertEqual(len(result[0].calls), 1)
        self.assertEqual(result[0].total_call_count, 1)

    def test_evaluate_department_matches_cleaned_api_name_to_personnel_name(self) -> None:
        result = evaluate_department(
            [CallRecord("Alaz (310)", None, dt("11:30"), 60, "1")],
            [Personnel(id=1, department_id=1, name="alaz", extension="310", is_active=True)],
            self.rules,
            self.report_date,
            dt("11:40"),
            TZ,
        )

        self.assertEqual(result[0].name, "alaz")
        self.assertEqual(len(result[0].calls), 1)
        self.assertEqual(result[0].total_call_count, 1)

    def test_evaluate_department_matches_normalized_agent_record_to_personnel(self) -> None:
        records = normalize_calls(
            [
                {
                    "Date": "2026-06-09",
                    "Time": "11:30:00",
                    "CallTimeSecond": "5",
                    "AgentName": "Alaz",
                    "AgentExtension": "310",
                }
            ],
            TZ,
        )

        result = evaluate_department(
            records,
            [Personnel(id=1, department_id=1, name="Alaz", extension="310", is_active=True)],
            self.rules,
            self.report_date,
            dt("11:40"),
            TZ,
        )

        self.assertEqual(result[0].name, "Alaz")
        self.assertEqual(len(result[0].calls), 1)
        self.assertEqual(result[0].total_call_count, 1)

    def test_evaluate_department_can_still_use_api_people_when_no_personnel_list_exists(self) -> None:
        result = evaluate_department(
            [
                call("Ali", "11:10", extension="1001"),
                call("Veli", "11:30", extension="2001"),
            ],
            [],
            self.rules,
            self.report_date,
            dt("11:40"),
            TZ,
        )

        self.assertEqual([evaluation.name for evaluation in result], ["Ali", "Veli"])

    def test_grid_call_after_work_start_is_not_treated_as_missing_call(self) -> None:
        records = normalize_calls(
            [
                {
                    "ARAMA TARİHİ": "09/06/2026",
                    "ARAMA SAATİ": "11:45:40",
                    "KONUŞMA SÜRESİ": "00:00:00",
                    "ÇALDIRMA SÜRESİ": "00:00:11",
                    "DAHİLİ ADI": "Ali -O",
                }
            ],
            TZ,
        )

        result = self.evaluate(records)

        self.assertFalse(any("Mesai başlangıcı ihlali: 11:10 sonrası çağrı yok" in violation for violation in result.violations))
        self.assertTrue(any("ilk çağrı 11:45" in violation for violation in result.violations))

    def test_filter_notified_violations_keeps_only_new_violations(self) -> None:
        evaluations = [
            PersonnelEvaluation(
                name="Ayşe",
                extension="1001",
                violations=["Mesai başlangıcı ihlali", "Güncel bekleme ihlali"],
            )
        ]

        filtered = _filter_notified_violations(evaluations, {("ayşe", "mesai başlangıcı ihlali")})

        self.assertEqual(filtered[0].violations, ["Güncel bekleme ihlali"])
        self.assertEqual(evaluations[0].violations, ["Mesai başlangıcı ihlali", "Güncel bekleme ihlali"])

    def test_violation_keys_are_normalized(self) -> None:
        evaluations = [
            PersonnelEvaluation(
                name="Ayşe",
                extension="1001",
                violations=["  Mesai   Başlangıcı İhlali  "],
            )
        ]

        self.assertEqual(_violation_keys(evaluations), [("ayşe", "mesai başlangıcı i̇hlali")])

    def test_current_idle_violation_key_ignores_elapsed_minutes(self) -> None:
        evaluations = [
            PersonnelEvaluation(
                name="Ayşe",
                extension="1001",
                violations=[
                    "Güncel bekleme ihlali: son çağrı 11:25 sonrası 95 dk bekleme var (limit 15 dk)",
                    "Güncel bekleme ihlali: son çağrı 11:25 sonrası 155 dk bekleme var (limit 15 dk)",
                ],
            )
        ]

        self.assertEqual(
            _violation_keys(evaluations),
            [("ayşe", "güncel bekleme ihlali"), ("ayşe", "güncel bekleme ihlali")],
        )

if __name__ == "__main__":
    unittest.main()