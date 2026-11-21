"""check_knowledge and the kb CLI: stale, unevidenced or malformed entries fail."""
import datetime as dtm

import pytest

from helpers import check_knowledge as c
from helpers import kb

TODAY = dtm.date(2026, 11, 22)

DA = """---
id: da-0001
title: Late order rows
tags: [orders, late-rows]
paths: [src/orders.sql]
status: active
created: 2026-11-01
last_verified: {verified}
evidence:
  - src/orders.sql::late row
supersedes: []
---

## Meaning

Rows held back land in a later partition.

## Counts

3 rows.

```sql
select count(*) from lake.shop__orders where updated_at::date < _dt;
```

## Terms

Late rows.

## Data quality

Take the latest updated_at.
"""

DE = """---
id: de-0001
title: One transaction per day
tags: [loader]
paths: []
status: active
created: 2026-11-01
last_verified: 2026-11-01
evidence: [src/orders.sql]
supersedes: []
---

## Rule

Load a day in one transaction.

## Why

No half-loaded day.

## How to apply

Rerun the loader.

## Example

loader --date 2026-01-02
"""

EVALS = """k: 3
floor: 1.0
cases:
  - {query: "rows that arrive late", expect: da-0001}
  - {query: "half loaded day transaction", expect: de-0001}
"""


def make_kb(root, da=None, de=DE, evals=EVALS, render=True):
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src/orders.sql").write_text("-- a late row never wins\nselect 1\n")
    base = root / ".agents/knowledge"
    (base / "entries/da").mkdir(parents=True, exist_ok=True)
    (base / "entries/de").mkdir(parents=True, exist_ok=True)
    (base / "evals").mkdir(parents=True, exist_ok=True)
    (base / "entries/da/da-0001-late-order-rows.md").write_text(
        da if da is not None else DA.format(verified="2026-11-20"))
    if de is not None:
        (base / "entries/de/de-0001-one-transaction.md").write_text(de)
    (base / "evals/retrieval.yaml").write_text(evals)
    if render:
        entries, _ = kb.load(root)
        for rel, text in kb.rendered(entries).items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text)
    return root


def errors(root, today=TODAY):
    return c.check(root, today)[0]


def test_repo_passes():
    assert c.check()[0] == []


def test_fixture_passes(tmp_path):
    assert errors(make_kb(tmp_path)) == []


def test_stale_da_entry_fails(tmp_path):
    root = make_kb(tmp_path, da=DA.format(verified="2026-08-01"))
    assert any("stale, last verified 2026-08-01" in e for e in errors(root))


def test_de_entry_lives_longer_than_da(tmp_path):
    root = make_kb(tmp_path)
    assert errors(root, dtm.date(2027, 6, 1)) == [
        ".agents/knowledge/entries/da/da-0001-late-order-rows.md: stale, last verified "
        "2026-11-20 (193 days; a da- entry is verified again within 90); re-check it and bump "
        "last_verified, or retire it"]


def test_expiry_warns_first(tmp_path):
    root = make_kb(tmp_path)
    errs, warns = c.check(root, dtm.date(2027, 2, 10))
    assert errs == [] and any("expires in 8 days" in w for w in warns)


def test_retired_entry_does_not_expire(tmp_path):
    da = DA.format(verified="2026-01-01").replace("status: active", "status: retired")
    assert errors(make_kb(tmp_path, da=da.replace("created: 2026-11-01", "created: 2026-01-01"))) == []


def test_unevidenced_entry_fails(tmp_path):
    da = DA.format(verified="2026-11-20").replace("evidence:\n  - src/orders.sql::late row\n",
                                                  "evidence: []\n")
    assert any("no evidence" in e for e in errors(make_kb(tmp_path, da=da)))


@pytest.mark.parametrize("item, expect", [
    ("src/missing.sql", "src/missing.sql does not exist"),
    ("src/orders.sql::early row", "does not contain 'early row'"),
    ("'src/orders.sql: late'", "does not exist"),
])
def test_evidence_that_does_not_resolve_fails(tmp_path, item, expect):
    da = DA.format(verified="2026-11-20").replace("src/orders.sql::late row", item)
    errs = errors(make_kb(tmp_path, da=da))
    assert any(expect in e for e in errs), errs


def test_unquoted_evidence_with_colon_fails(tmp_path):
    da = DA.format(verified="2026-11-20").replace("src/orders.sql::late row", "src/orders.sql: late")
    assert any("is not a string" in e for e in errors(make_kb(tmp_path, da=da)))


def test_missing_frontmatter_field_fails(tmp_path):
    da = DA.format(verified="2026-11-20").replace("supersedes: []\n", "")
    assert any("missing supersedes" in e for e in errors(make_kb(tmp_path, da=da)))


def test_no_frontmatter_fails(tmp_path):
    root = make_kb(tmp_path, da="# just a note\n", render=False)
    assert any("no frontmatter" in e for e in errors(root))


@pytest.mark.parametrize("old, new, expect", [
    ("id: da-0001", "id: da-1", "is not de-NNNN or da-NNNN"),
    ("id: da-0001", "id: de-0002", "belongs in entries/de/"),
    ("status: active", "status: draft", "status 'draft'"),
    ("tags: [orders, late-rows]", "tags: []", "tags is a non-empty list"),
    ("created: 2026-11-01", "created: 2026-11-21", "created is after last_verified"),
    ("paths: [src/orders.sql]", "paths: [src/gone.sql]", "path 'src/gone.sql' does not exist"),
    ("supersedes: []", "supersedes: [da-0009]", "supersedes 'da-0009', which does not exist"),
    ("supersedes: []", "supersedes: [de-0001]", "which is still active"),
    ("## Terms\n\nLate rows.\n", "", "'## Terms' is missing"),
    ("```sql\nselect count(*) from lake.shop__orders where updated_at::date < _dt;\n```\n", "",
     "no ```sql block"),
])
def test_bad_frontmatter_or_body_fails(tmp_path, old, new, expect):
    da = DA.format(verified="2026-11-20").replace(old, new)
    errs = errors(make_kb(tmp_path, da=da))
    assert any(expect in e for e in errs), errs


def test_future_verification_fails(tmp_path):
    root = make_kb(tmp_path, da=DA.format(verified="2026-12-01"))
    assert any("in the future" in e for e in errors(root))


def test_duplicate_id_fails(tmp_path):
    root = make_kb(tmp_path)
    (root / ".agents/knowledge/entries/da/da-0001-copy.md").write_text(DA.format(verified="2026-11-20"))
    assert any("is also used by" in e for e in errors(root))


def test_hand_edited_generated_doc_fails(tmp_path):
    root = make_kb(tmp_path)
    doc = root / kb.GENERATED["da"]
    doc.write_text(doc.read_text() + "\nhand edit\n")
    assert errors(root) == [f"{kb.GENERATED['da'].as_posix()} is out of date; run "
                            f"`uv run python -m helpers.kb render`"]


def test_retrieval_below_floor_fails(tmp_path):
    evals = EVALS + '  - {query: "zebra migration", expect: de-0001}\n'
    assert any("below the floor" in e for e in errors(make_kb(tmp_path, evals=evals)))


def test_search_ranks_the_matching_entry_first(tmp_path):
    entries, _ = kb.load(make_kb(tmp_path))
    assert [e.id for _, e in kb.search(entries, "late arriving rows")][0] == "da-0001"
    assert kb.search(entries, "zebra") == []


def test_cli_new_list_show_render(tmp_path, capsys):
    root = make_kb(tmp_path)
    assert kb.main(["new", "da", "What voucher codes mean"], root=root) == 0
    path = capsys.readouterr().out.strip()
    assert path == ".agents/knowledge/entries/da/da-0002-voucher-codes-mean.md"
    text = (root / path).read_text()
    assert "id: da-0002" in text and "## Counts" in text
    assert kb.main(["list", "--kind", "da"], root=root) == 0
    assert "da-0002" in capsys.readouterr().out
    assert kb.main(["show", "de-0001"], root=root) == 0
    assert "## Rule" in capsys.readouterr().out
    assert kb.main(["show", "de-0404"], root=root) == 1
    # the new entry is a TODO stub without evidence: it must not pass
    assert any("da-0002" in e and "no evidence" in e for e in errors(root))
    assert kb.main(["render"], root=root) == 0
    assert "da-0002" in (root / kb.GENERATED["index"]).read_text()


def test_repo_search_finds_defects():
    entries, _ = kb.load()
    top = [e.id for _, e in kb.search(entries, "orphan product keys", 1)]
    assert top == ["da-0004"]
