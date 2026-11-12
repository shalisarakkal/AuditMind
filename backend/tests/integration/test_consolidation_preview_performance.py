"""Bounded preview scaling exercise, not a SaaS concurrency/load qualification."""
import json
import statistics
import time
import uuid
from datetime import timedelta

from sqlalchemy import event, insert, select

from app.models.finding import Finding
from app.models.finding_observation import FindingObservation
from app.models.finding_identity_binding import ObservationIdentityBinding
from tests.conftest import requires_db
from tests.integration.test_finding_consolidation_foundation import native, preview, select_pair

pytestmark = requires_db


def test_preview_at_observation_limit_has_constant_queries_and_bounded_response(client, db_session, native):
    n = native
    # Large scanner text stays in PostgreSQL. Responses contain only excerpts.
    large = 'Synthetic performance text \u03b1 ' * 40000
    for row in db_session.scalars(select(Finding)):
        row.description = large
    db_session.commit()
    select_pair(client, n)
    measurements = []

    def measure(label):
        counts, elapsed, sizes = [], [], []
        for _ in range(3):
            statements = []
            def capture(conn, cursor, statement, parameters, context, many):
                statements.append(statement)
            event.listen(db_session.get_bind(), 'before_cursor_execute', capture)
            started = time.perf_counter()
            try:
                result = preview(client, n)
            finally:
                elapsed.append(time.perf_counter() - started)
                event.remove(db_session.get_bind(), 'before_cursor_execute', capture)
            assert result.status_code == 200, result.text
            assert result.json()['prerequisites_met'] is True
            counts.append(len(statements)); sizes.append(len(result.content))
            assert all(len(row['description']) <= 2000 for row in result.json()['findings'])
        measurement = dict(case=label, queries=max(counts), response_bytes=max(sizes),
            median_seconds=round(statistics.median(elapsed), 4), max_seconds=round(max(elapsed), 4))
        measurements.append(measurement)
        assert max(elapsed) < 30, measurement  # Broad hang guard, not an SLA.
        assert max(sizes) < 40000, measurement
        return measurement

    baseline = measure('two_observations_large_descriptions')
    source = n['source']
    binding = db_session.scalar(select(ObservationIdentityBinding).where(
        ObservationIdentityBinding.observation_id == source.id).order_by(ObservationIdentityBinding.version.desc()))
    observations, bindings = [], []
    for i in range(998):
        identifier = uuid.uuid4()
        observations.append(dict(id=identifier, org_id=source.org_id, finding_id=source.finding_id,
            import_id=source.import_id, scan_id=source.scan_id, occurrence=i+100, source_row=i+100,
            source=source.source, scan_type=source.scan_type, profile=source.profile, filename=source.filename,
            recorded_at=source.recorded_at-timedelta(seconds=i+1), asset_identity=source.asset_identity,
            source_identity=source.source_identity, reconciliation_eligible=False, ineligibility_reasons=[],
            payload=source.payload))
        bindings.append(dict(id=uuid.uuid4(), org_id=source.org_id, observation_id=identifier,
            version=1, state='bound', tool_id=binding.tool_id, canonical_asset_id=binding.canonical_asset_id,
            context=binding.context, rationale='Synthetic retained review', actor_id=binding.actor_id,
            actor_label=binding.actor_label))
    db_session.execute(insert(FindingObservation), observations)
    db_session.execute(insert(ObservationIdentityBinding), bindings)
    db_session.commit()
    maximum = measure('thousand_reviewed_observations_large_descriptions')
    assert maximum['queries'] <= baseline['queries'] + 2, measurements
    assert maximum['response_bytes'] <= baseline['response_bytes'] + 512, measurements
    assert preview(client, n).json()['dependency_summary']['resource_counts']['observation'] == 1000
    print('CONSOLIDATION_PREVIEW_MEASUREMENTS=' + json.dumps(measurements, sort_keys=True))
