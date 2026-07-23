# Events (automatic behavior)

{py:mod}`autostorage.events` registers SQLAlchemy ORM event listeners at import time. Because
`autostorage.database` imports `.events` (for its side effect of registering these listeners)
before opening any `Database`, everything on this page applies to **any** session touching
these models — not just calls made through `Database`'s own methods.

Listeners are registered two ways, and the choice between them matters:

- **Mapper-level** (`before_insert`/`before_update`/`before_delete` on a specific model) — runs
  once per row of that type, as part of that row's own flush step.
- **Session-level** (`before_flush` on `Session`) — runs once per flush, before any mapper-level
  events, with access to the whole pending change set (`session.new`/`dirty`/`deleted`).

Three listeners below are session-level specifically because they need to **mutate a different,
already-clean object** than the one that triggered them (e.g. deleting a `HessianRow` needs to
update a `StationaryPointRow.is_valid` that isn't itself being inserted/updated/deleted).
SQLAlchemy silently drops attribute changes made to other, already-clean objects from within a
mapper-level `before_delete`/`before_insert`/`before_update` handler — those objects aren't part
of the acting object's already-computed flush plan. A session-level `before_flush` listener runs
before that plan is fixed, so changes it makes are picked up.

## Shape validation

```{eval-rst}
.. autofunction:: autostorage.events.verify_gradient_shape
   :no-index:
.. autofunction:: autostorage.events.verify_hessian_shape
   :no-index:
```

Both run on `before_insert`/`before_update` for their row type. `GradientRow.value` must have
shape `(3 * atom_count,)`; `HessianRow.value` must be `(3 * atom_count, 3 * atom_count)`, where
`atom_count` comes from the row's linked `GeometryRow`. A mismatch raises
{py:class}`~autostorage.exc.ResultShapeError` — which surfaces at `flush()`/`commit()` time, not
at the point the row was constructed or `add()`-ed.

Both listeners resolve the geometry via a shared helper, `_resolve_geometry`, rather than
reading `target.geometry` directly: if a row was built with only `geometry_id=...` set (not the
`.geometry` relationship), the relationship stays unpopulated until the ORM syncs it — reading
it directly would let shape validation be silently skipped for a row that does have a geometry.
`_resolve_geometry` falls back to `session.get(GeometryRow, target.geometry_id)` in that case.
The same pattern reappears below for `StepRow`'s stage relationships
(`_resolve_stage`).

## Stationary-point validity

```{eval-rst}
.. autofunction:: autostorage.events.validate_geometry_orders
   :no-index:
.. autofunction:: autostorage.events.revalidate_geometry_orders_on_hessian_delete
   :no-index:
```

`StationaryPointRow.is_valid` is derived, not set directly by application code. It's recomputed
by `_recompute_geometry_stationary_validity(geometry)` whenever the set of `HessianRow`s
attached to a geometry changes:

1. Collect the geometry's `HessianRow`s (minus any passed via `excluding=`, see below).
2. Compute each Hessian's `order` (the count of negative harmonic frequencies — see
   {py:attr}`~autostorage.models.HessianRow.order`) and take the set of distinct orders.
3. If more than one distinct order is present, raise `ValueError` — the geometry's Hessians
   disagree, which can't be reconciled automatically.
4. Otherwise, for every `StationaryPointRow` on that geometry, set `is_valid = (stationary.order
   == expected_order)`, where `expected_order` is the one agreed-upon Hessian order.

This recompute is wired to three triggers:

- `validate_geometry_orders` — a mapper-level `before_insert`/`before_update` listener on both
  `StationaryPointRow` and `HessianRow`, covering the common case of inserting/editing either
  side.
- `revalidate_geometry_orders_on_hessian_delete` — a **session-level** `before_flush` listener
  that reacts to `HessianRow` deletions. It's session-level (not a mapper `before_delete`
  listener) for the reason given in the section intro: it needs to write to
  `StationaryPointRow.is_valid` on objects other than the one being deleted. It passes the
  about-to-be-deleted Hessians as `excluding=` to `_recompute_geometry_stationary_validity`,
  since `geometry.hessians` still includes them at `before_flush` time (the `DELETE` hasn't been
  issued to the database yet).

If a geometry has no Hessians, or no `StationaryPointRow`s, the recompute is a no-op — `is_valid`
keeps whatever value it already had.

## Geometry immutability

```{eval-rst}
.. autofunction:: autostorage.events.verify_geometry_immutable_fields
   :no-index:
```

Once a `GeometryRow` has been inserted, `symbols` and `coordinates` can never be changed —
attempting to modify either raises `ValueError` on the next `flush()`/`commit()`. `charge` and
`spin` remain freely mutable. This is enforced via `sqlalchemy.orm.attributes.get_history`,
which reports whether a field has pending added/deleted values since it was loaded; if the field
has never been touched, `get_history` reports no change and the update passes.

The reason: `GradientRow`/`HessianRow` shape checks (above) and Hessian order consensus are
computed once, against the geometry as it existed when those results were saved. Silently
allowing `symbols`/`coordinates` to change afterward would invalidate checks already performed
without re-running them.

## Automatic identity attachment

```{eval-rst}
.. autofunction:: autostorage.events.add_inchi_identities
   :no-index:
```

A session-level `before_flush` listener. For every new (`session.new`) `StationaryPointRow`, it:

1. Computes an InChI `IdentityRow` from the point's geometry via
   `IdentityRow.from_geometry(geo=..., algorithm=Algorithm.RDKIT_INCHI)`. If this raises
   `ValueError` (e.g. `automol`/RDKit can't derive an InChI for the geometry), the point is
   skipped — no identity is attached and no error propagates.
2. Batches all resulting `(algorithm, value)` pairs into a single `tuple_(...).in_(...)` query
   against existing `IdentityRow`s, so N new stationary points cost one lookup query rather than
   N.
3. If a matching InChI `IdentityRow` already exists, reuses it (appends the *existing* row to
   `obj.identities`) instead of creating a duplicate — this is what backs the
   `unique_identity` constraint on `(kind, algorithm, value)` staying meaningful in practice
   rather than being hit as an integrity error.
4. Otherwise, attaches the newly-computed InChI row, and additionally derives a SMILES string
   via `Algorithm.RDKIT_SMILES`. The SMILES is **not** stored as its own `IdentityRow` — it's
   attached as an `IdentityExtraRow(identity=inchi, attribute="smiles", value=...)` on the InChI
   identity just created. If SMILES derivation raises `ValueError`, it's silently skipped (the
   InChI identity is still attached).

## Conformer grouping

```{eval-rst}
.. autofunction:: autostorage.events.assign_conformer_ids
   :no-index:
```

Also a session-level `before_flush` listener, run after `add_inchi_identities` has had a chance
to populate InChI identities on new stationary points (both are registered against the same
event; SQLAlchemy invokes same-event listeners in registration order, and `events.py` defines
`add_inchi_identities` first).

For each new `StationaryPointRow` that doesn't already have an IRMSD-kind identity
(`Algorithm.IRMSD.kind`) but does have an InChI identity:

1. Look at the InChI identity's other attached stationary points ("peers") — points that share
   the same InChI, i.e. the same constitutional/stereo identity.
2. Compare the new point's geometry against each peer's via
   `automol.geom.is_duplicate_conformer`.
3. If one matches, reuse that peer's IRMSD identity (its conformer-group id) via
   `_matching_conformer_identity` — same conformer, same group.
4. Otherwise, allocate a new group id: `max(existing IRMSD values cast to int) + 1`, or `1` if
   none exist yet, and create a new IRMSD `IdentityRow` with that value.

```{note}
Group-id allocation assumes single-writer semantics, consistent with `Database`'s documented
[non-thread-safety](database.md#session-model-and-thread-safety). If that assumption is
violated (e.g. two processes/threads racing against the same on-disk database), the
`unique_identity` constraint on `IdentityRow` turns a racing duplicate group id into an
`IntegrityError` at commit — rather than silently merging two distinct conformer groups under
one id.
```

Within a single flush, multiple new non-duplicate points increment `next_group_id` locally
(instead of re-querying `MAX(...)` for each one), so N new unrelated conformers correctly get N
distinct, consecutive group ids from one query.

## Reaction step consistency

```{eval-rst}
.. autofunction:: autostorage.events.verify_stage_order_and_barrierless
   :no-index:
.. autofunction:: autostorage.events.verify_stage_ts_consistency
   :no-index:
```

Both are mapper-level `before_insert`/`before_update` listeners on `StepRow`:

- `verify_stage_order_and_barrierless` sorts `stage_id1 < stage_id2` (swapping them if
  necessary) so every `StepRow` satisfies the `chk_stage_order` `CheckConstraint` regardless of
  which order the caller passed `stage1`/`stage2` in, and derives
  `is_barrierless = not stage_id_ts` — callers never set `is_barrierless` directly.
- `verify_stage_ts_consistency` rejects `stage1`/`stage2` if either is a transition-state stage
  (`StageRow.is_ts`), and rejects `stage_ts` if it *isn't* one, raising `ValueError` on any
  mismatch.

Both resolve stages via `_resolve_stage`, the `StepRow` analogue of `_resolve_geometry` above:
if only a `stage_id*` foreign key was set (not the `stage*`/`stage_ts` relationship), it falls
back to `session.get(StageRow, stage_id)` so the check isn't skipped for a step that does
reference a stage.
