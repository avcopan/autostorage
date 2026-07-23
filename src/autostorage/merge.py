"""Merge one database's contents into another, with validation at merge time."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import inspect as sa_inspect
from sqlmodel import SQLModel, func, select

from .events import AUTO_MANAGED_IDENTITY_ALGORITHMS
from .models import IdentityExtraRow, IdentityRow, ModelRow, StationaryIdentityLink

if TYPE_CHECKING:
    from .database import Database

__all__ = ["MergeReport", "merge_databases"]


@dataclass(frozen=True, slots=True)
class MergeReport:
    """Summary of a `merge_databases` call.

    Attributes
    ----------
    copied
        New rows created in the target database, by table name.
    reused
        Source rows deduplicated onto an existing target row, by table name
        (only ``model`` and ``identity`` support dedup).
    """

    copied: dict[str, int]
    reused: dict[str, int]


def merge_databases(
    target: "Database", source: "Database", *, commit: bool = True
) -> MergeReport:
    """Copy `source`'s contents into `target`, validating and deduplicating.

    Rows are copied with freshly-assigned primary keys and remapped foreign
    keys. `ModelRow` and non-auto-managed `IdentityRow`s are deduplicated
    against `target`'s existing content; everything else is copied fresh.

    InChI/conformer identities are deliberately skipped here: inserting each
    source `StationaryPointRow` fresh lets `autostorage.events`'s flush
    listeners regenerate and dedup them against `target`'s live state, so a
    conformer shared by both databases collapses onto one identity. Every
    copied row passes through normal ORM validation.

    Only `flush()` is used until the end, so an error partway through
    leaves `target` unchanged.

    Parameters
    ----------
    target
        Database to copy rows into.
    source
        Database to copy rows from. Only ever read, never modified.
    commit, optional
        If True (default), commit once every table has copied successfully.
        If False, leave flushed-but-uncommitted for the caller.

    Returns
    -------
    MergeReport
        Per-table counts of rows copied and reused.
    """
    _check_mergeable(target, source)

    id_map: dict[type[SQLModel], dict[int, int]] = {}
    copied: dict[str, int] = {}
    reused: dict[str, int] = {}
    skipped_identity_ids: set[int] = set()

    for cls in _ordered_models():
        if cls is ModelRow:
            _copy_models(
                target=target,
                source=source,
                id_map=id_map,
                copied=copied,
                reused=reused,
            )
        elif cls is IdentityRow:
            skipped_identity_ids = _copy_identities(
                target=target,
                source=source,
                id_map=id_map,
                copied=copied,
                reused=reused,
            )
        elif cls is IdentityExtraRow:
            rows = [
                row
                for row in source.exec_all(select(IdentityExtraRow))
                if row.identity_id not in skipped_identity_ids
            ]
            _copy_table(
                IdentityExtraRow, rows, target=target, id_map=id_map, copied=copied
            )
        elif cls is StationaryIdentityLink:
            rows = [
                row
                for row in source.exec_all(select(StationaryIdentityLink))
                if row.identity_id not in skipped_identity_ids
            ]
            _copy_table(
                StationaryIdentityLink,
                rows,
                target=target,
                id_map=id_map,
                copied=copied,
            )
        else:
            _copy_table(
                cls,
                source.exec_all(select(cls)),
                target=target,
                id_map=id_map,
                copied=copied,
            )

    if commit:
        target.commit()
    else:
        target.flush()

    return MergeReport(copied=copied, reused=reused)


def _is_same_database(a: "Database", b: "Database") -> bool:
    """Return whether `a` and `b` refer to the same underlying database.

    In-memory databases (path ``":memory:"``) never count as a match;
    on-disk `Database`s match if they resolve to the same file.
    """
    if a is b:
        return True
    if str(a.path) == ":memory:" or str(b.path) == ":memory:":
        return False
    return a.path.resolve() == b.path.resolve()


def _reflected_schema(db: "Database") -> dict[str, set[str]]:
    """Return the actual on-disk table/column names for `db`."""
    inspector = sa_inspect(db.engine)
    return {
        table_name: {column["name"] for column in inspector.get_columns(table_name)}
        for table_name in inspector.get_table_names()
    }


def _check_mergeable(target: "Database", source: "Database") -> None:
    """Reject a merge that can't safely proceed.

    Raises
    ------
    ValueError
        If `source` and `target` are the same database, or either is
        missing an expected table/column (e.g. an outdated schema).
    """
    if _is_same_database(target, source):
        msg = "Cannot merge a database into itself."
        raise ValueError(msg)

    expected = {
        table.name: {column.name for column in table.columns}
        for table in SQLModel.metadata.tables.values()
    }
    for db, label in ((source, "source"), (target, "target")):
        actual = _reflected_schema(db)
        for table_name, expected_columns in expected.items():
            if table_name not in actual:
                msg = f"{label} database is missing table {table_name!r}."
                raise ValueError(msg)
            missing_columns = expected_columns - actual[table_name]
            if missing_columns:
                msg = (
                    f"{label} database's {table_name!r} table is missing "
                    f"column(s) {sorted(missing_columns)!r}."
                )
                raise ValueError(msg)


def _mapped_classes() -> dict[str, type[SQLModel]]:
    """Map each table name to its mapped `SQLModel` class."""
    mapping: dict[str, type[SQLModel]] = {}
    for mapper in SQLModel._sa_registry.mappers:  # noqa: SLF001
        table = getattr(mapper.class_, "__table__", None)
        if table is not None:
            mapping[table.name] = mapper.class_
    return mapping


def _ordered_models() -> list[type[SQLModel]]:
    """Return every mapped table's `SQLModel` class, in FK-safe insertion order."""
    mapping = _mapped_classes()
    return [mapping[table.name] for table in SQLModel.metadata.sorted_tables]


def _fk_targets(cls: type[SQLModel]) -> list[tuple[str, type[SQLModel]]]:
    """Return `(column name, target class)` for each foreign key column on `cls`."""
    mapping = _mapped_classes()
    return [
        (column.name, mapping[fk.column.table.name])
        for column in cls.__table__.columns  # ty:ignore[unresolved-attribute]
        for fk in column.foreign_keys
    ]


def _copy_row(
    row: SQLModel, *, id_map: dict[type[SQLModel], dict[int, int]]
) -> SQLModel:
    """Build a new, unsaved row copying `row`'s content with FKs remapped."""
    cls = type(row)
    content = row.model_dump(exclude={"id", "created_at", "updated_at"})
    for column_name, target_cls in _fk_targets(cls):
        old_id = content.get(column_name)
        if old_id is not None:
            content[column_name] = id_map[target_cls][old_id]
    return cls(**content)


def _copy_table(
    cls: type[SQLModel],
    rows: list[SQLModel],
    *,
    target: "Database",
    id_map: dict[type[SQLModel], dict[int, int]],
    copied: dict[str, int],
) -> None:
    """Copy `rows` (all of type `cls`) into `target`, remapping FKs via `id_map`."""
    if not rows:
        return

    new_rows = [_copy_row(row, id_map=id_map) for row in rows]
    target.add_all(new_rows)
    target.flush()

    if "id" in cls.model_fields:
        id_map[cls] = {
            row.id: new_row.id  # ty:ignore[unresolved-attribute]
            for row, new_row in zip(rows, new_rows, strict=True)
        }

    copied[cls.__tablename__] = len(new_rows)  # ty:ignore[invalid-assignment]


def _table_count(db: "Database", cls: type[SQLModel]) -> int:
    """Return the number of rows currently in `cls`'s table."""
    return db.exec_first(select(func.count()).select_from(cls)) or 0


def _copy_models(
    *,
    target: "Database",
    source: "Database",
    id_map: dict[type[SQLModel], dict[int, int]],
    copied: dict[str, int],
    reused: dict[str, int],
) -> None:
    """Find-or-create every source `ModelRow` against `target`."""
    rows = source.exec_all(select(ModelRow))
    if not rows:
        return

    before = _table_count(target, ModelRow)
    mapping: dict[int, int] = {}
    for row in rows:
        new_row = ModelRow.find_or_create(
            target,
            program=row.program,
            method=row.method,
            program_version=row.program_version,
            basis=row.basis,
            commit=False,
        )
        mapping[row.id] = new_row.id  # ty:ignore[invalid-assignment]

    id_map[ModelRow] = mapping
    created = _table_count(target, ModelRow) - before
    copied["model"] = created
    reused["model"] = len(rows) - created


def _copy_identities(
    *,
    target: "Database",
    source: "Database",
    id_map: dict[type[SQLModel], dict[int, int]],
    copied: dict[str, int],
    reused: dict[str, int],
) -> set[int]:
    """Find-or-create every non-auto-managed source `IdentityRow` against `target`.

    Auto-managed identities (`AUTO_MANAGED_IDENTITY_ALGORITHMS`) are left for
    `autostorage.events`'s flush listeners to regenerate instead.

    Returns
    -------
    set[int]
        Source-side ids of skipped identities, so callers can filter out
        rows referencing them (identity extras, stationary-identity links).
    """
    rows = source.exec_all(select(IdentityRow))
    skipped_ids: set[int] = set()
    if not rows:
        return skipped_ids

    before = _table_count(target, IdentityRow)
    mapping: dict[int, int] = {}
    handled = 0
    for row in rows:
        if row.algorithm in AUTO_MANAGED_IDENTITY_ALGORITHMS:
            skipped_ids.add(row.id)
            continue
        handled += 1
        new_row = IdentityRow.find_or_create(
            target, algorithm=row.algorithm, value=row.value, commit=False
        )
        mapping[row.id] = new_row.id  # ty:ignore[invalid-assignment]

    id_map[IdentityRow] = mapping
    created = _table_count(target, IdentityRow) - before
    copied["identity"] = created
    reused["identity"] = handled - created
    return skipped_ids
