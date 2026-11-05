import pytest
from scripts.rehearse_recovery import canonical_check, digest, verify_archive


def test_pg_dump_enum_array_cast_rewrite_is_equivalent():
    source = "CHECK (status = ANY ((ARRAY['open'::character varying, 'closed'::character varying])::text[]))"
    restored = "CHECK (status = ANY (ARRAY[('open'::character varying)::text, ('closed'::character varying)::text]))"
    assert canonical_check(source) == canonical_check(restored)


def test_canonicalization_keeps_literal_values_and_operators():
    source = "CHECK (status = ANY ((ARRAY['open'::character varying])::text[]))"
    assert canonical_check(source) != canonical_check(source.replace("'open'","'closed'"))
    assert canonical_check(source) != canonical_check(source.replace("= ANY","<> ALL"))
    quoted = "CHECK (status = ANY ((ARRAY['literal::character varying'::character varying])::text[]))"
    assert "'literal::character varying'" in canonical_check(quoted)


def test_canonicalization_leaves_other_types_and_length_casts_unchanged():
    for expression in ("CHECK (n = ANY ((ARRAY[1,2])::integer[]))",
                       "CHECK (x = ('oversized'::character varying(3))::text)"):
        assert canonical_check(expression) == expression


def test_partial_unique_index_preserves_keys_and_predicate_values():
    prefix = "CREATE UNIQUE INDEX ix ON public.jobs USING btree (org_id) WHERE "
    source = prefix+"status = ANY ((ARRAY['pending'::character varying])::text[])"
    target = prefix+"status = ANY (ARRAY[('pending'::character varying)::text])"
    assert canonical_check(source) == canonical_check(target)
    assert canonical_check(source) != canonical_check(target.replace("(org_id)","(id)"))


def test_archive_integrity_gate_rejects_corrupted_bytes(tmp_path):
    archive = tmp_path/"synthetic.dump"
    original = b"Synthetic backup integrity fixture"
    archive.write_bytes(original)
    verify_archive(archive,digest(original))
    archive.write_bytes(original+b" changed")
    with pytest.raises(ValueError,match="checksum mismatch"):
        verify_archive(archive,digest(original))
