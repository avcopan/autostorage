"""Autostorage utilities."""

import io
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from automol import geom
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .exc import MissingPrimaryKeyError
from .models import (
    EnergyRow,
    GeometryRow,
    HessianRow,
    ModelRow,
    StageRow,
    StationaryPointRow,
    StepRow,
)

if TYPE_CHECKING:
    from .database import Database

# CODATA Hartree -> kcal/mol; `automol.utils.constants` has no molar-energy
# conversion, and adding one there is out of scope for this feature.
HARTREE_TO_KCAL_PER_MOL = 627.5094740631

# Ground-state electronic levels (energy in 1/cm, degeneracy) for species whose
# low-lying spin-orbit splitting is significant enough to matter for a
# master-equation calculation. Every other species defaults to a single
# ground-state level at 0 1/cm with degeneracy `spin + 1`. Keyed by Hill
# formula (`automol.geom.hill_formula`) so extending this to other radicals
# later is a one-line addition.
_ELECTRONIC_LEVELS_BY_HILL_FORMULA: dict[str, tuple[tuple[float, int], ...]] = {
    "HO": ((0.0, 2), (140.0, 2)),
}

# Symmetry numbers are computed from `GeometryRow.symmetry_number` wherever a
# geometry is available. The one exception is a barrierless step's TS block,
# which has no geometry at all (see `_render_barrierless_placeholder_block`)
# and so falls back to this placeholder, which must be checked by hand before
# the generated file is used for a real calculation.
_SYMMETRY_NUMBER_PLACEHOLDER = (
    "1  ! TODO(autostorage): placeholder -- "
    "no TS geometry to compute a symmetry number from, verify manually"
)

# PES plot rendering constants. Grayscale-only: a single reaction path isn't a
# categorical comparison, so hue would encode nothing. Dashed + muted gray
# means "flagged" (missing energy), matching the flag-don't-crash philosophy
# already used by `_render_zero_energy_block`'s TODO placeholder.
_LEVEL_HALF_WIDTH = 0.3
_LEVEL_COLOR = "black"
_LEVEL_LINEWIDTH = 2.5
_CONNECTOR_LINEWIDTH = 1.25
_FLAGGED_COLOR = "0.6"
_FLAGGED_LINESTYLE = "--"
_MISSING_ENERGY_SENTINEL_KCAL = 0.0
_MISSING_ENERGY_SUFFIX = " (no energy data)"
_LABEL_FONTSIZE = 9
_Y_AXIS_LABEL = "Relative Energy (kcal/mol)"
_X_AXIS_LABEL = "Reaction Coordinate"
_DEFAULT_FIGSIZE = (6.0, 4.5)


@dataclass(frozen=True, slots=True)
class _FragmentData:
    """Resolved geometry/frequency data for one stationary point of a species."""

    stationary: StationaryPointRow
    geometry: GeometryRow
    frequencies: tuple[float, ...] | None


@dataclass(frozen=True, slots=True)
class _SpeciesData:
    """Resolved rendering data for one non-TS stage (a well or bimolecular state)."""

    stage: StageRow
    label: str
    name: str
    zero_energy_kcal: float | None
    fragments: tuple[_FragmentData, ...]


def _require_stage_id(stage: StageRow) -> int:
    """Return `stage.id`, raising if the stage hasn't been persisted."""
    if stage.id is None:
        raise MissingPrimaryKeyError([stage])
    return stage.id


def _collect_stages(steps: Sequence[StepRow]) -> list[StageRow]:
    """Return unique stages referenced by `steps`, in first-encounter order."""
    stages: list[StageRow] = []
    seen_ids: set[int] = set()
    for step in steps:
        for stage in (step.stage1, step.stage2, step.stage_ts):
            if stage is None:
                continue
            stage_id = _require_stage_id(stage)
            if stage_id not in seen_ids:
                seen_ids.add(stage_id)
                stages.append(stage)
    return stages


def _auto_labels(stages: Sequence[StageRow]) -> dict[int, str]:
    """Assign auto-generated `W#`/`P#` labels to stages, in first-encounter order."""
    labels: dict[int, str] = {}
    well_count = 0
    bimolecular_count = 0
    for stage in stages:
        if stage.is_ts:
            continue
        stage_id = _require_stage_id(stage)
        if len(stage.stationaries) == 1:
            well_count += 1
            labels[stage_id] = f"W{well_count}"
        else:
            bimolecular_count += 1
            labels[stage_id] = f"P{bimolecular_count}"
    return labels


def _auto_barrier_labels(steps: Sequence[StepRow]) -> list[str]:
    """Assign sequential `B#` labels, one per step, in `steps` order."""
    return [f"B{i}" for i in range(1, len(steps) + 1)]


def _auto_name(stage: StageRow) -> str:
    """Return a Hill-formula-based comment name for a stage's fragment(s)."""
    fragments = sorted(stage.stationaries, key=lambda s: s.id or 0)
    return " + ".join(geom.hill_formula(f.geometry) for f in fragments)


def _resolve_label(
    stage: StageRow, auto: dict[int, str], override: dict[int, str]
) -> str:
    """Return the override label for `stage`, falling back to its auto label."""
    stage_id = _require_stage_id(stage)
    return override.get(stage_id, auto[stage_id])


def _resolve_name(stage: StageRow, override: dict[int, str]) -> str:
    """Return the override comment name for `stage`, falling back to `_auto_name`."""
    stage_id = _require_stage_id(stage)
    if stage_id in override:
        return override[stage_id]
    return _auto_name(stage)


def _energy_hartree(db: "Database", geo: GeometryRow, model: ModelRow) -> float | None:
    """Return the Hartree energy of `geo` at `model`, or `None` if not found."""
    if geo.id is None or model.id is None:
        raise MissingPrimaryKeyError([geo, model])
    energy = EnergyRow.query(db, geo=geo, model=model)
    return energy.value if energy is not None else None


def _relative_energy_kcal(
    value_hartree: float | None, ref_hartree: float
) -> float | None:
    """Convert a Hartree energy to kcal/mol relative to `ref_hartree`."""
    if value_hartree is None:
        return None
    return (value_hartree - ref_hartree) * HARTREE_TO_KCAL_PER_MOL


def _resolve_ref_hartree(
    db: "Database", ref: StationaryPointRow, model: ModelRow
) -> float:
    """Return the Hartree energy of `ref` at `model`, raising if not found."""
    ref_hartree = _energy_hartree(db, ref.geometry, model)
    if ref_hartree is None:
        msg = (
            f"No EnergyRow found for reference geometry {ref.geometry.id} "
            f"at model {model.id}."
        )
        raise ValueError(msg)
    return ref_hartree


def _electronic_levels(geo: GeometryRow) -> tuple[tuple[float, int], ...]:
    """Return `(energy_cm1, degeneracy)` ground-state electronic levels for `geo`.

    Ground-state only (energy 0, degeneracy = `spin + 1`) for every species,
    except the small lookup table in `_ELECTRONIC_LEVELS_BY_HILL_FORMULA`.
    """
    formula = geom.hill_formula(geo)
    if formula in _ELECTRONIC_LEVELS_BY_HILL_FORMULA:
        return _ELECTRONIC_LEVELS_BY_HILL_FORMULA[formula]
    return ((0.0, geo.spin + 1),)


def _indent(text: str, spaces: int) -> str:
    """Indent every line of `text` by `spaces` spaces."""
    prefix = " " * spaces
    return "\n".join(prefix + line for line in text.splitlines())


def _format_number_columns(
    values: Sequence[float], *, per_line: int = 3, width: int = 10, precision: int = 2
) -> str:
    """Render `values` right-aligned in fixed-width columns, `per_line` per row."""
    lines = []
    for i in range(0, len(values), per_line):
        chunk = values[i : i + per_line]
        lines.append("".join(f"{v:>{width}.{precision}f}" for v in chunk))
    return "\n".join(lines)


def _render_geometry_block(geo: GeometryRow) -> str:
    """Render a MESS `Geometry[angstrom]` block."""
    lines = [f"Geometry[angstrom]  {geo.atom_count}"]
    lines.extend(
        f"{symbol}  {x:.6f}  {y:.6f}  {z:.6f}"
        for symbol, (x, y, z) in zip(geo.symbols, geo.coordinates, strict=True)
    )
    return "\n".join(lines)


def _render_frequencies_block(frequencies: tuple[float, ...]) -> str:
    """Render a MESS `Frequencies[1/cm]` block."""
    header = f"Frequencies[1/cm]  {len(frequencies)}"
    if not frequencies:
        return header
    return f"{header}\n{_format_number_columns(frequencies)}"


def _render_electronic_levels_block(geo: GeometryRow) -> str:
    """Render a MESS `ElectronicLevels[1/cm]` block."""
    levels = _electronic_levels(geo)
    lines = [f"ElectronicLevels[1/cm]  {len(levels)}"]
    lines.extend(f"{energy:.1f}  {degeneracy}" for energy, degeneracy in levels)
    return "\n".join(lines)


def _render_zero_energy_block(
    energy_kcal: float | None, *, keyword: str = "ZeroEnergy"
) -> str:
    """Render a MESS `ZeroEnergy`/`GroundEnergy[kcal/mol]` line."""
    if energy_kcal is None:
        return (
            f"{keyword}[kcal/mol]  0.00  ! TODO(autostorage): no EnergyRow found "
            "at requested model -- fill in manually"
        )
    return f"{keyword}[kcal/mol]  {energy_kcal:.2f}"


def _render_fragment_zero_energy_block() -> str:
    """Render a fragment's `ZeroEnergy[1/cm]` line.

    Always 0 -- an isolated fragment has no energy reference of its own; the
    enclosing `Bimolecular` block's `GroundEnergy[kcal/mol]` line carries the
    actual relative energy of the pair.
    """
    return "ZeroEnergy[1/cm]  0"


def _render_core_rigidrotor_block(symmetry_number: int | None) -> str:
    """Render a MESS `Core RigidRotor` block.

    Falls back to a flagged placeholder when `symmetry_number` is `None`
    (only for a barrierless step's TS block, which has no geometry to
    compute one from).
    """
    factor = (
        _SYMMETRY_NUMBER_PLACEHOLDER if symmetry_number is None else symmetry_number
    )
    return f"Core RigidRotor\n  SymmetryFactor  {factor}\nEnd"


def _render_fragment_block(fragment: _FragmentData, label: str) -> str:
    """Render a `Fragment` sub-block within a `Bimolecular` species."""
    parts = [
        f"Fragment  {label}",
        _indent("RRHO", 2),
        _indent(_render_geometry_block(fragment.geometry), 4),
        _indent(_render_core_rigidrotor_block(fragment.geometry.symmetry_number), 4),
    ]
    if fragment.frequencies:
        parts.append(_indent(_render_frequencies_block(fragment.frequencies), 4))
    parts.append(_indent(_render_fragment_zero_energy_block(), 4))
    parts.append(_indent(_render_electronic_levels_block(fragment.geometry), 4))
    parts.append(_indent("End", 2))
    return "\n".join(parts)


def _render_species_block(
    fragment: _FragmentData, zero_energy_kcal: float | None
) -> str:
    """Render a well's `Species` sub-block."""
    parts = [
        "Species",
        _indent("RRHO", 2),
        _indent(_render_geometry_block(fragment.geometry), 4),
        _indent(_render_core_rigidrotor_block(fragment.geometry.symmetry_number), 4),
    ]
    if fragment.frequencies:
        parts.append(_indent(_render_frequencies_block(fragment.frequencies), 4))
    parts.append(_indent(_render_zero_energy_block(zero_energy_kcal), 4))
    parts.append(_indent(_render_electronic_levels_block(fragment.geometry), 4))
    parts.append(_indent("End", 2))
    return "\n".join(parts)


def _render_well_block(species: _SpeciesData) -> str:
    """Render a `Well` block for a single-fragment stage."""
    (fragment,) = species.fragments
    header = f"Well  {species.label}  # {species.name}"
    body = _render_species_block(fragment, species.zero_energy_kcal)
    return f"{header}\n{_indent(body, 2)}\nEnd"


def _render_bimolecular_block(species: _SpeciesData) -> str:
    """Render a `Bimolecular` block for a multi-fragment stage."""
    header = f"Bimolecular  {species.label}  # {species.name}"
    fragment_blocks = "\n".join(
        _indent(_render_fragment_block(f, geom.hill_formula(f.geometry)), 2)
        for f in species.fragments
    )
    ground_energy = _indent(
        _render_zero_energy_block(species.zero_energy_kcal, keyword="GroundEnergy"), 2
    )
    return f"{header}\n{fragment_blocks}\n{ground_energy}\nEnd"


def _build_fragment_data(
    db: "Database", stationary: StationaryPointRow, *, model: ModelRow
) -> _FragmentData:
    """Resolve geometry and frequency data for one fragment stationary point."""
    geometry = stationary.geometry
    if geometry.id is None or model.id is None:
        raise MissingPrimaryKeyError([geometry, model])
    hessian = HessianRow.query(db, geo=geometry, model=model)
    frequencies = hessian.harmonic_frequencies if hessian is not None else None
    return _FragmentData(
        stationary=stationary, geometry=geometry, frequencies=frequencies
    )


def _build_species_data(  # noqa: PLR0913
    db: "Database",
    stage: StageRow,
    *,
    model: ModelRow,
    ref_hartree: float,
    label: str,
    name: str,
) -> _SpeciesData:
    """Resolve all rendering data for a well/bimolecular stage."""
    fragments = tuple(
        _build_fragment_data(db, s, model=model)
        for s in sorted(stage.stationaries, key=lambda s: s.id or 0)
    )
    if len(fragments) == 1:
        value_hartree = _energy_hartree(db, fragments[0].geometry, model)
        zero_energy_kcal = _relative_energy_kcal(value_hartree, ref_hartree)
    else:
        values_hartree = [
            _energy_hartree(db, fragment.geometry, model) for fragment in fragments
        ]
        zero_energy_kcal = (
            None
            if any(value is None for value in values_hartree)
            else _relative_energy_kcal(sum(values_hartree), ref_hartree)
        )
    return _SpeciesData(
        stage=stage,
        label=label,
        name=name,
        zero_energy_kcal=zero_energy_kcal,
        fragments=fragments,
    )


def _render_barrier_block(  # noqa: PLR0913
    db: "Database",
    step: StepRow,
    barrier_label: str,
    species1: _SpeciesData,
    species2: _SpeciesData,
    *,
    model: ModelRow,
    ref_hartree: float,
) -> str:
    """Render a `Barrier` block for a step with a transition state."""
    ts_stage = step.stage_ts
    (ts_stationary,) = ts_stage.stationaries
    ts_geometry = ts_stationary.geometry
    hessian = HessianRow.query(db, geo=ts_geometry, model=model)
    real_frequencies = (
        tuple(f for f in hessian.harmonic_frequencies if f > 0.0)
        if hessian is not None
        else None
    )
    value_hartree = _energy_hartree(db, ts_geometry, model)
    zero_energy_kcal = _relative_energy_kcal(value_hartree, ref_hartree)

    header = (
        f"Barrier  {barrier_label}  {species1.label}  {species2.label}"
        f"  # {species1.name} = {species2.name}"
    )
    parts = [
        _indent("RRHO", 2),
        _indent(_render_geometry_block(ts_geometry), 4),
        _indent(_render_core_rigidrotor_block(ts_geometry.symmetry_number), 4),
    ]
    if real_frequencies:
        parts.append(_indent(_render_frequencies_block(real_frequencies), 4))
    parts.append(_indent(_render_zero_energy_block(zero_energy_kcal), 4))
    parts.append(_indent(_render_electronic_levels_block(ts_geometry), 4))
    body = "\n".join(parts)
    return f"{header}\n{body}\nEnd"


def _render_barrierless_placeholder_block(
    step: StepRow,
    barrier_label: str,
    species1: _SpeciesData,
    species2: _SpeciesData,
) -> str:
    """Render a placeholder `Barrier` block for a step with no transition state.

    MESS's barrierless treatment (phase-space theory / variational flux)
    needs long-range potential parameters that autostorage does not store;
    this output is not directly MESS-runnable and must be completed by hand.
    """
    del step  # kept in the signature for symmetry with `_render_barrier_block`
    energies = [
        e
        for e in (species1.zero_energy_kcal, species2.zero_energy_kcal)
        if e is not None
    ]
    zero_energy_kcal = max(energies) if energies else None

    header = (
        f"Barrier  {barrier_label}  {species1.label}  {species2.label}"
        f"  # {species1.name} = {species2.name}"
    )
    lines = [
        "! TODO(autostorage): barrierless step -- no transition state exists "
        "in the database.",
        "! Fill in a PhaseSpaceTheory/Variational flux-parameter model by hand,",
        "! or replace this Barrier block with the appropriate MESS "
        "barrierless-channel construct.",
        _indent("RRHO", 2),
        _indent("Geometry[angstrom]", 4),
        _indent(
            "! TODO(autostorage): no TS geometry -- supply variational "
            "geometries manually",
            6,
        ),
        _indent(_render_core_rigidrotor_block(None), 4),
        _indent("Frequencies[1/cm]  0", 4),
        _indent(
            "! TODO(autostorage): no TS frequencies -- supply manually or "
            "replace with a Variational/PST model",
            6,
        ),
        _indent(_render_zero_energy_block(zero_energy_kcal), 4),
        _indent("ElectronicLevels[1/cm]  1", 4),
        _indent("0.0  1", 6),
    ]
    return f"{header}\n" + "\n".join(lines) + "\nEnd"


def export_mess_input(  # noqa: PLR0913
    db: "Database",
    steps: Sequence[StepRow],
    *,
    ref: StationaryPointRow,
    model: ModelRow,
    labels: dict[int, str] | None = None,
    names: dict[int, str] | None = None,
) -> str:
    """Render `steps` as MESS `Well`/`Bimolecular`/`Barrier` input blocks.

    Wells and bimolecular species are derived from the unique, non-TS stages
    referenced by `steps` (first-encounter order), auto-labeled `W1, W2, ...`
    (single-stationary stages) / `P1, P2, ...` (multi-stationary stages) and
    commented with a Hill-formula-based name, unless overridden via `labels`/
    `names` (keyed by `StageRow.id`). Each step becomes one `Barrier` block,
    auto-labeled `B1, B2, ...` in `steps` order; a step with no transition
    state (`StepRow.is_barrierless`) instead gets a placeholder block flagged
    with `TODO(autostorage)` comments, since MESS's barrierless treatment
    needs long-range potential parameters this schema doesn't store.

    All energies (`ZeroEnergy`/`GroundEnergy[kcal/mol]`) are the bare
    electronic energy (`EnergyRow.value`) at `model`, relative to `ref` --
    not ZPE-corrected, since MESS applies its own ZPE handling from the
    `Frequencies` block. Symmetry numbers (`SymmetryFactor`) are computed
    from each species'/barrier's geometry via `GeometryRow.symmetry_number`,
    except for a barrierless step's TS block, which has no geometry and so
    gets a flagged placeholder instead. This function does not emit
    `Model`/`EnergyRelaxation`/`CollisionFrequency` blocks -- those are
    simulation setup, not stored reaction data, and must be prepended by the
    caller.

    Parameters
    ----------
    db
        Database to query energies and Hessians from.
    steps
        Elementary reaction steps to include, in output order.
    ref
        Stationary point defining the zero of energy (0.0 kcal/mol).
    model
        Level of theory used for every energy and frequency lookup.
    labels, optional
        Override MESS labels, keyed by `StageRow.id`.
    names, optional
        Override comment names, keyed by `StageRow.id`.

    Returns
    -------
    The full MESS input text for the given steps.

    Raises
    ------
    ValueError
        No `EnergyRow` found for `ref` at `model`.

    Examples
    --------
    >>> import numpy as np
    >>> from autostorage import (
    ...     CalcType,
    ...     CalculationRow,
    ...     Database,
    ...     EnergyRow,
    ...     GeometryRow,
    ...     ModelRow,
    ...     StageRow,
    ...     StationaryPointRow,
    ...     StepRow,
    ... )
    >>> db = Database(":memory:")
    >>> model = ModelRow(program="ORCA", method="b3lyp")
    >>> calc = CalculationRow(model=model, calc_type=CalcType.OPT)
    >>> geo1 = GeometryRow(
    ...     symbols=["O", "H"],
    ...     coordinates=np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.97]]),
    ...     charge=0,
    ...     spin=1,
    ... )
    >>> geo2 = GeometryRow(
    ...     symbols=["O", "H"],
    ...     coordinates=np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 1.50]]),
    ...     charge=0,
    ...     spin=1,
    ... )
    >>> s1 = StationaryPointRow(geometry=geo1, calculation=calc)
    >>> s2 = StationaryPointRow(geometry=geo2, calculation=calc)
    >>> db.add_all([s1, s2])
    >>> db.commit()
    >>> db.add_all(
    ...     [
    ...         EnergyRow(geometry=geo1, calculation=calc, value=-75.0),
    ...         EnergyRow(geometry=geo2, calculation=calc, value=-74.9),
    ...     ]
    ... )
    >>> db.commit()
    >>> stage1 = StageRow(stationaries=[s1])
    >>> stage2 = StageRow(stationaries=[s2])
    >>> step = StepRow(stage1=stage1, stage2=stage2)
    >>> db.add(step)
    >>> db.commit()
    >>> text = export_mess_input(db, [step], ref=s1, model=model)
    >>> "Well  W1" in text and "Well  W2" in text
    True
    >>> "TODO(autostorage): barrierless step" in text
    True
    >>> db.close()
    """
    labels = labels or {}
    names = names or {}

    ref_hartree = _resolve_ref_hartree(db, ref, model)

    stages = _collect_stages(steps)
    auto_labels = _auto_labels(stages)

    species_by_stage_id: dict[int, _SpeciesData] = {}
    for stage in stages:
        if stage.is_ts:
            continue
        species_by_stage_id[_require_stage_id(stage)] = _build_species_data(
            db,
            stage,
            model=model,
            ref_hartree=ref_hartree,
            label=_resolve_label(stage, auto_labels, labels),
            name=_resolve_name(stage, names),
        )

    blocks = []
    for stage in stages:
        if stage.is_ts:
            continue
        species = species_by_stage_id[_require_stage_id(stage)]
        if len(species.fragments) == 1:
            blocks.append(_render_well_block(species))
        else:
            blocks.append(_render_bimolecular_block(species))

    barrier_labels = _auto_barrier_labels(steps)
    for step, barrier_label in zip(steps, barrier_labels, strict=True):
        species1 = species_by_stage_id[_require_stage_id(step.stage1)]
        species2 = species_by_stage_id[_require_stage_id(step.stage2)]
        if step.is_barrierless:
            blocks.append(
                _render_barrierless_placeholder_block(
                    step, barrier_label, species1, species2
                )
            )
        else:
            blocks.append(
                _render_barrier_block(
                    db,
                    step,
                    barrier_label,
                    species1,
                    species2,
                    model=model,
                    ref_hartree=ref_hartree,
                )
            )

    return "\n".join(blocks) + "\n"


@dataclass(frozen=True, slots=True)
class _LevelPlacement:
    """Resolved y-position and flagged-status of one drawn level."""

    y_kcal: float
    flagged: bool


@dataclass(frozen=True, slots=True)
class PESPlot:
    """A rendered potential energy surface diagram.

    Attributes
    ----------
    figure
        The rendered figure.
    axes
        The axes the diagram was drawn into.
    """

    figure: Figure
    axes: Axes

    def _repr_png_(self) -> bytes:
        """Return a PNG-encoded snapshot of `figure`, for Jupyter's rich display."""
        buffer = io.BytesIO()
        self.figure.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
        return buffer.getvalue()

    def save(self, path: str | Path, **savefig_kwargs: Any) -> None:  # noqa: ANN401
        """Save `figure` to `path`; format is inferred from its suffix."""
        savefig_kwargs.setdefault("bbox_inches", "tight")
        self.figure.savefig(path, **savefig_kwargs)


def _draw_level(
    axes: Axes, x: float, energy_kcal: float | None, *, label: str, name: str
) -> _LevelPlacement:
    """Draw one flat energy-level segment (species well/bimolecular or TS peak)."""
    flagged = energy_kcal is None
    y = _MISSING_ENERGY_SENTINEL_KCAL if flagged else energy_kcal
    color = _FLAGGED_COLOR if flagged else _LEVEL_COLOR
    axes.plot(
        [x - _LEVEL_HALF_WIDTH, x + _LEVEL_HALF_WIDTH],
        [y, y],
        color=color,
        linewidth=_LEVEL_LINEWIDTH,
        linestyle=_FLAGGED_LINESTYLE if flagged else "-",
        solid_capstyle="butt",
        zorder=3,
    )
    text = f"{label}\n{name}{_MISSING_ENERGY_SUFFIX if flagged else ''}"
    axes.annotate(
        text,
        xy=(x, y),
        xytext=(0, 6),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=_LABEL_FONTSIZE,
        color=color,
        annotation_clip=False,
    )
    return _LevelPlacement(y_kcal=y, flagged=flagged)


def _draw_connector(  # noqa: PLR0913
    axes: Axes,
    x1: float,
    placement1: _LevelPlacement,
    x2: float,
    placement2: _LevelPlacement,
    *,
    linestyle: str = "-",
) -> None:
    """Draw a connector line between two levels' inner edges.

    Sorts by x first -- a step's `stage1`/`stage2` are ordered by ascending
    database id, not by x-position, so `x1 < x2` cannot be assumed.
    """
    (left_x, left), (right_x, right) = sorted(
        [(x1, placement1), (x2, placement2)], key=lambda pair: pair[0]
    )
    flagged = left.flagged or right.flagged
    axes.plot(
        [left_x + _LEVEL_HALF_WIDTH, right_x - _LEVEL_HALF_WIDTH],
        [left.y_kcal, right.y_kcal],
        color=_FLAGGED_COLOR if flagged else _LEVEL_COLOR,
        linewidth=_CONNECTOR_LINEWIDTH,
        linestyle=_FLAGGED_LINESTYLE if flagged else linestyle,
        zorder=2,
    )


def _annotate_barrier_label(axes: Axes, x: float, y: float, label: str) -> None:
    """Annotate a barrierless connector's midpoint with its `B#` label."""
    axes.annotate(
        label,
        xy=(x, y),
        xytext=(0, 6),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=_LABEL_FONTSIZE,
        color=_FLAGGED_COLOR,
        style="italic",
        annotation_clip=False,
    )


def plot_pes(  # noqa: PLR0913
    db: "Database",
    steps: Sequence[StepRow],
    *,
    ref: StationaryPointRow,
    model: ModelRow,
    labels: dict[int, str] | None = None,
    names: dict[int, str] | None = None,
    ax: Axes | None = None,
) -> PESPlot:
    r"""Render `steps` as a potential energy surface diagram.

    Wells and bimolecular species are derived the same way as
    `export_mess_input`: the unique, non-TS stages referenced by `steps`
    (first-encounter order), auto-labeled `W1, W2, ...` / `P1, P2, ...` and
    named by Hill formula, unless overridden via `labels`/`names` (keyed by
    `StageRow.id`). Each is drawn as a flat horizontal "level" segment
    positioned along an unlabeled, ordinal x-axis (first-encounter order --
    *not* a guaranteed chemical reaction direction, since stage insertion
    order need not match "reactant to product"). Each step becomes a peak at
    its transition state (labeled `B1, B2, ...` in `steps` order, positioned
    midway between its two stages), connected to both stages by diagonal
    lines; a barrierless step instead draws one direct dashed connector with
    no peak.

    All energies are the bare electronic energy (`EnergyRow.value`) at
    `model`, relative to `ref`, in kcal/mol. A species or transition state
    with no `EnergyRow` at `model` is drawn at 0.0 kcal/mol in a flagged
    (dashed, muted gray) style with " (no energy data)" appended to its
    label, rather than being omitted or raising.

    Parameters
    ----------
    db
        Database to query energies from.
    steps
        Elementary reaction steps to include, in output order.
    ref
        Stationary point defining the zero of energy (0.0 kcal/mol).
    model
        Level of theory used for every energy lookup.
    labels, optional
        Override labels, keyed by `StageRow.id`.
    names, optional
        Override names, keyed by `StageRow.id`.
    ax, optional
        Axes to draw into. If `None`, a new figure/axes is created.

    Returns
    -------
    Wrapper holding the rendered figure/axes.

    Raises
    ------
    ValueError
        No `EnergyRow` found for `ref` at `model`.

    Examples
    --------
    >>> import numpy as np
    >>> from autostorage import (
    ...     CalcType,
    ...     CalculationRow,
    ...     Database,
    ...     EnergyRow,
    ...     GeometryRow,
    ...     ModelRow,
    ...     StageRow,
    ...     StationaryPointRow,
    ...     StepRow,
    ... )
    >>> db = Database(":memory:")
    >>> model = ModelRow(program="ORCA", method="b3lyp")
    >>> calc = CalculationRow(model=model, calc_type=CalcType.OPT)
    >>> geo1 = GeometryRow(
    ...     symbols=["O", "H"],
    ...     coordinates=np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.97]]),
    ...     charge=0,
    ...     spin=1,
    ... )
    >>> geo2 = GeometryRow(
    ...     symbols=["O", "H"],
    ...     coordinates=np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 1.50]]),
    ...     charge=0,
    ...     spin=1,
    ... )
    >>> s1 = StationaryPointRow(geometry=geo1, calculation=calc)
    >>> s2 = StationaryPointRow(geometry=geo2, calculation=calc)
    >>> db.add_all([s1, s2])
    >>> db.commit()
    >>> db.add_all(
    ...     [
    ...         EnergyRow(geometry=geo1, calculation=calc, value=-75.0),
    ...         EnergyRow(geometry=geo2, calculation=calc, value=-74.9),
    ...     ]
    ... )
    >>> db.commit()
    >>> stage1 = StageRow(stationaries=[s1])
    >>> stage2 = StageRow(stationaries=[s2])
    >>> step = StepRow(stage1=stage1, stage2=stage2)
    >>> db.add(step)
    >>> db.commit()
    >>> plot = plot_pes(db, [step], ref=s1, model=model)
    >>> [line.get_linestyle() for line in plot.axes.lines].count("--")
    1
    >>> sorted(text.get_text().splitlines()[0] for text in plot.axes.texts)
    ['B1', 'W1', 'W2']
    >>> plot._repr_png_().startswith(b"\x89PNG")
    True
    >>> db.close()
    """
    labels = labels or {}
    names = names or {}

    ref_hartree = _resolve_ref_hartree(db, ref, model)

    stages = _collect_stages(steps)
    auto_labels = _auto_labels(stages)
    non_ts_stages = [stage for stage in stages if not stage.is_ts]
    x_by_stage_id = {
        _require_stage_id(stage): float(i) for i, stage in enumerate(non_ts_stages)
    }

    species_by_stage_id: dict[int, _SpeciesData] = {}
    for stage in non_ts_stages:
        species_by_stage_id[_require_stage_id(stage)] = _build_species_data(
            db,
            stage,
            model=model,
            ref_hartree=ref_hartree,
            label=_resolve_label(stage, auto_labels, labels),
            name=_resolve_name(stage, names),
        )

    if ax is None:
        figure = Figure(figsize=_DEFAULT_FIGSIZE)
        FigureCanvasAgg(figure)
        axes = figure.add_subplot()
    else:
        axes = ax
        figure = cast("Figure", ax.figure)

    placements_by_stage_id: dict[int, _LevelPlacement] = {}
    for stage in non_ts_stages:
        stage_id = _require_stage_id(stage)
        species = species_by_stage_id[stage_id]
        placements_by_stage_id[stage_id] = _draw_level(
            axes,
            x_by_stage_id[stage_id],
            species.zero_energy_kcal,
            label=species.label,
            name=species.name,
        )

    barrier_labels = _auto_barrier_labels(steps)
    for step, barrier_label in zip(steps, barrier_labels, strict=True):
        id1 = _require_stage_id(step.stage1)
        id2 = _require_stage_id(step.stage2)
        x1, x2 = x_by_stage_id[id1], x_by_stage_id[id2]
        placement1 = placements_by_stage_id[id1]
        placement2 = placements_by_stage_id[id2]

        if step.is_barrierless:
            _draw_connector(
                axes, x1, placement1, x2, placement2, linestyle=_FLAGGED_LINESTYLE
            )
            _annotate_barrier_label(
                axes,
                (x1 + x2) / 2,
                (placement1.y_kcal + placement2.y_kcal) / 2,
                barrier_label,
            )
        else:
            ts_stage = step.stage_ts
            (ts_stationary,) = ts_stage.stationaries
            ts_value_hartree = _energy_hartree(db, ts_stationary.geometry, model)
            ts_energy_kcal = _relative_energy_kcal(ts_value_hartree, ref_hartree)
            x_ts = (x1 + x2) / 2
            ts_placement = _draw_level(
                axes,
                x_ts,
                ts_energy_kcal,
                label=barrier_label,
                name=_resolve_name(ts_stage, names),
            )
            _draw_connector(axes, x1, placement1, x_ts, ts_placement)
            _draw_connector(axes, x_ts, ts_placement, x2, placement2)

    axes.set_ylabel(_Y_AXIS_LABEL)
    axes.set_xlabel(_X_AXIS_LABEL)
    axes.set_xticks([])
    axes.spines[["top", "right", "bottom"]].set_visible(False)
    axes.grid(axis="y", color="0.85", linewidth=0.8, zorder=0)
    axes.set_axisbelow(True)
    axes.margins(x=0.15, y=0.15)

    return PESPlot(figure=figure, axes=axes)
