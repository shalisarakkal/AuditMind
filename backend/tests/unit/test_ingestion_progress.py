from app.services.ingestion_progress import ProgressReporter


def test_reports_slow_row_progress_before_a_whole_batch_finishes():
    now = [0.0]
    seen = []
    report = ProgressReporter(lambda *args: seen.append(args), clock=lambda: now[0])
    report('writing', 0, 500000)
    for row in range(1, 101):
        now[0] = row / 10
        report('writing', row, 500000)
    assert seen[1] == ('writing', 10, 500000)
    assert len(seen) == 11  # initial, then once per second, below the old 2,000 rows


def test_fast_rows_are_throttled_but_phase_and_final_counts_are_immediate():
    seen = []
    report = ProgressReporter(lambda *args: seen.append(args), clock=lambda: 0.0)
    report('reading', 2000, 2000)
    report('reading', 4000, 4000)  # estimated reading totals are not completion
    report('preparing', 0, 10000)
    report('writing', 0, 10000)
    for row in range(1, 10001):
        report('writing', row, 10000)
    report('writing', 10000, 10000)  # identical final count is not written twice
    report('saving', 0, 0)
    assert seen == [('reading', 2000, 2000), ('preparing', 0, 10000),
                    ('writing', 0, 10000), ('writing', 10000, 10000), ('saving', 0, 0)]


def test_an_unchanged_count_does_not_publish_new_progress_timestamp():
    now = [0.0]
    seen = []
    report = ProgressReporter(lambda *args: seen.append(args), clock=lambda: now[0])
    report('writing', 123, 1000)
    now[0] = 30.0
    report('writing', 123, 1000)
    assert seen == [('writing', 123, 1000)]
