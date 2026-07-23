"""Autostorage MESS export tests."""

import re

import numpy as np
import pytest
from numpy.random import Generator

from autostorage import (
    CalculationRow,
    Database,
    EnergyRow,
    GeometryRow,
    HessianRow,
    StageRow,
    StationaryPointRow,
    StepRow,
)
from autostorage.utils import HARTREE_TO_KCAL_PER_MOL, export_mess_input


def _stationary(
    database: Database,
    calculation: CalculationRow,
    geometry: GeometryRow,
    *,
    order: int = 0,
) -> StationaryPointRow:
    """Create, persist, and return a stationary point for `geometry`."""
    stationary = StationaryPointRow(
        calculation=calculation, geometry=geometry, order=order
    )
    database.add(stationary)
    database.commit()
    return stationary


def _with_energy(
    database: Database, calculation: CalculationRow, geometry: GeometryRow, value: float
) -> None:
    """Persist an `EnergyRow` for `geometry` at `calculation`'s model."""
    database.add(EnergyRow(geometry=geometry, calculation=calculation, value=value))
    database.commit()


def _diatomic(symbols: list[str], distance: float, *, spin: int = 0) -> GeometryRow:
    """Build a simple two-atom `GeometryRow` along the z-axis."""
    return GeometryRow(
        symbols=symbols,
        coordinates=np.array([[0.0, 0.0, 0.0], [0.0, 0.0, distance]]),
        charge=0,
        spin=spin,
    )


def _species_section(text: str, label: str) -> str:
    """Return the `Well`/`Bimolecular` block in `text` for the given label."""
    for keyword in ("Well", "Bimolecular"):
        marker = f"{keyword}  {label}"
        if marker in text:
            start = text.index(marker)
            break
    else:
        msg = f"No species block found for label {label!r}."
        raise AssertionError(msg)

    rest = text[start + len(marker) :]
    boundaries = [
        start + len(marker) + rest.index(kw)
        for kw in ("\nWell  ", "\nBimolecular  ", "\nBarrier  ")
        if kw in rest
    ]
    end = min(boundaries) if boundaries else len(text)
    return text[start:end]


def _barrier_section(text: str, label: str) -> str:
    """Return the `Barrier` block in `text` for the given label (to end of text)."""
    marker = f"Barrier  {label}"
    return text[text.index(marker) :]


def test__export_well_bimolecular_barrier_round_trip(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that a well + bimolecular + barrier network renders all block types."""
    database.add(calculation_row)
    database.commit()

    ref = _stationary(database, calculation_row, geometry_row)
    _with_energy(database, calculation_row, geometry_row, -76.0)
    well_stage = StageRow(stationaries=[ref])

    frag1_geo = GeometryRow(
        symbols=["N", "H", "H"],
        coordinates=np.array([[0.0, 0.0, 0.0], [0.0, 0.8, -0.5], [0.0, -0.8, -0.5]]),
        charge=0,
        spin=1,
    )
    frag2_geo = GeometryRow(
        symbols=["H", "C", "O"],
        coordinates=np.array([[0.0, 1.2, 0.0], [0.0, 0.0, 0.0], [1.1, -0.6, 0.0]]),
        charge=0,
        spin=1,
    )
    frag1 = _stationary(database, calculation_row, frag1_geo)
    frag2 = _stationary(database, calculation_row, frag2_geo)
    _with_energy(database, calculation_row, frag1_geo, -55.6)
    _with_energy(database, calculation_row, frag2_geo, -20.3)
    bimolecular_stage = StageRow(stationaries=[frag1, frag2])

    ts_geo = GeometryRow(
        symbols=["N", "H", "H"],
        coordinates=np.array([[0.0, 0.0, 0.0], [0.0, 0.9, -0.5], [0.0, -0.9, -0.5]]),
        charge=0,
        spin=1,
    )
    ts = _stationary(database, calculation_row, ts_geo, order=1)
    _with_energy(database, calculation_row, ts_geo, -75.5)
    ts_stage = StageRow(stationaries=[ts], is_ts=True)

    step = StepRow(stage1=well_stage, stage2=bimolecular_stage, stage_ts=ts_stage)
    database.add(step)
    database.commit()

    text = export_mess_input(database, [step], ref=ref, model=calculation_row.model)

    expected_fragment_count = 2

    assert "Well  W1" in text
    assert "Bimolecular  P1" in text
    assert text.count("Fragment  ") == expected_fragment_count
    barrier_section = _barrier_section(text, "B1")
    assert "W1" in barrier_section.splitlines()[0]
    assert "P1" in barrier_section.splitlines()[0]


def test__export_zero_energy_relative_to_reference(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that ZeroEnergy values are computed relative to the reference energy."""
    database.add(calculation_row)
    database.commit()

    ref = _stationary(database, calculation_row, geometry_row)
    other_geo = _diatomic(["H", "H"], 0.74)
    other = _stationary(database, calculation_row, other_geo)

    ref_value = -76.000
    other_value = -75.950
    _with_energy(database, calculation_row, geometry_row, ref_value)
    _with_energy(database, calculation_row, other_geo, other_value)

    step = StepRow(
        stage1=StageRow(stationaries=[ref]), stage2=StageRow(stationaries=[other])
    )
    database.add(step)
    database.commit()

    text = export_mess_input(database, [step], ref=ref, model=calculation_row.model)

    expected = (other_value - ref_value) * HARTREE_TO_KCAL_PER_MOL
    ref_section = _species_section(text, "W1")
    other_section = _species_section(text, "W2")
    ref_match = re.search(r"ZeroEnergy\[kcal/mol\]\s+(-?\d+\.\d+)", ref_section)
    other_match = re.search(r"ZeroEnergy\[kcal/mol\]\s+(-?\d+\.\d+)", other_section)
    assert ref_match is not None
    assert other_match is not None
    assert float(ref_match.group(1)) == pytest.approx(0.0, abs=1e-2)
    assert float(other_match.group(1)) == pytest.approx(expected, abs=1e-2)


def test__export_oh_electronic_levels_special_case(
    database: Database, calculation_row: CalculationRow
) -> None:
    """Test the OH spin-orbit electronic-levels special case and the fallback."""
    database.add(calculation_row)
    database.commit()

    oh_geo = _diatomic(["O", "H"], 0.97, spin=1)
    other_geo = _diatomic(["H", "H"], 0.74)
    oh = _stationary(database, calculation_row, oh_geo)
    other = _stationary(database, calculation_row, other_geo)
    _with_energy(database, calculation_row, oh_geo, -75.7)
    _with_energy(database, calculation_row, other_geo, -1.2)

    oh_stage = StageRow(stationaries=[oh])
    other_stage = StageRow(stationaries=[other])
    step = StepRow(stage1=oh_stage, stage2=other_stage)
    database.add(step)
    database.commit()

    assert oh_stage.id is not None
    assert other_stage.id is not None
    labels = {oh_stage.id: "WOH", other_stage.id: "WOTHER"}
    text = export_mess_input(
        database, [step], ref=oh, model=calculation_row.model, labels=labels
    )

    oh_section = _species_section(text, "WOH")
    other_section = _species_section(text, "WOTHER")

    assert "ElectronicLevels[1/cm]  2" in oh_section
    assert "0.0  2" in oh_section
    assert "140.0  2" in oh_section

    assert "ElectronicLevels[1/cm]  1" in other_section
    assert "0.0  1" in other_section


def test__export_barrierless_placeholder(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that a barrierless step renders a flagged placeholder Barrier block."""
    database.add(calculation_row)
    database.commit()

    ref = _stationary(database, calculation_row, geometry_row)
    other_geo = _diatomic(["H", "H"], 0.74)
    other = _stationary(database, calculation_row, other_geo)
    _with_energy(database, calculation_row, geometry_row, -76.0)
    _with_energy(database, calculation_row, other_geo, -1.0)

    step = StepRow(
        stage1=StageRow(stationaries=[ref]), stage2=StageRow(stationaries=[other])
    )
    database.add(step)
    database.commit()

    assert step.is_barrierless

    text = export_mess_input(database, [step], ref=ref, model=calculation_row.model)

    barrier_section = _barrier_section(text, "B1")
    assert "TODO(autostorage): barrierless step" in barrier_section
    assert "Frequencies[1/cm]  0" in barrier_section


def test__export_custom_labels_and_names_override(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that label/name overrides apply only to the given stage ids."""
    database.add(calculation_row)
    database.commit()

    ref = _stationary(database, calculation_row, geometry_row)
    other_geo = _diatomic(["H", "H"], 0.74)
    other = _stationary(database, calculation_row, other_geo)
    _with_energy(database, calculation_row, geometry_row, -76.0)
    _with_energy(database, calculation_row, other_geo, -1.0)

    ref_stage = StageRow(stationaries=[ref])
    step = StepRow(stage1=ref_stage, stage2=StageRow(stationaries=[other]))
    database.add(step)
    database.commit()

    assert ref_stage.id is not None
    text = export_mess_input(
        database,
        [step],
        ref=ref,
        model=calculation_row.model,
        labels={ref_stage.id: "X1"},
        names={ref_stage.id: "custom name"},
    )

    assert "Well  X1  # custom name" in text

    well_labels = re.findall(r"^Well {2}(\S+)", text, re.MULTILINE)
    assert "X1" in well_labels
    other_labels = [label for label in well_labels if label != "X1"]
    assert len(other_labels) == 1
    assert re.fullmatch(r"W\d+", other_labels[0])


def test__export_ts_excludes_imaginary_frequency(
    database: Database,
    calculation_row: CalculationRow,
    geometry_row: GeometryRow,
    rng: Generator,
) -> None:
    """Test that a Barrier block's Frequencies exclude the imaginary TS mode."""
    database.add(calculation_row)
    database.commit()

    ref = _stationary(database, calculation_row, geometry_row)
    other_geo = _diatomic(["H", "H"], 0.74)
    other = _stationary(database, calculation_row, other_geo)

    ts_geo = GeometryRow(
        symbols=["H", "O", "H"],
        coordinates=np.array([[0, 0, 0.9], [0, 0, 0], [0.9, 0, 0]]),
        charge=0,
        spin=0,
    )
    ts = _stationary(database, calculation_row, ts_geo, order=1)

    n = ts_geo.atom_count
    ts_hessian = HessianRow(
        calculation=calculation_row,
        geometry=ts_geo,
        value=rng.uniform(size=(3 * n, 3 * n)),
    )
    database.add(ts_hessian)
    database.commit()

    _with_energy(database, calculation_row, geometry_row, -76.0)
    _with_energy(database, calculation_row, other_geo, -75.9)
    _with_energy(database, calculation_row, ts_geo, -75.8)

    expected_positive_count = sum(1 for f in ts_hessian.harmonic_frequencies if f > 0.0)
    assert ts_hessian.order >= 1

    step = StepRow(
        stage1=StageRow(stationaries=[ref]),
        stage2=StageRow(stationaries=[other]),
        stage_ts=StageRow(stationaries=[ts], is_ts=True),
    )
    database.add(step)
    database.commit()

    text = export_mess_input(database, [step], ref=ref, model=calculation_row.model)

    barrier_section = _barrier_section(text, "B1")
    match = re.search(r"Frequencies\[1/cm\]\s+(\d+)", barrier_section)
    assert match is not None
    assert int(match.group(1)) == expected_positive_count


def test__export_missing_energy_renders_todo(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that a species missing an EnergyRow renders a TODO instead of raising."""
    database.add(calculation_row)
    database.commit()

    ref = _stationary(database, calculation_row, geometry_row)
    other_geo = _diatomic(["H", "H"], 0.74)
    other = _stationary(database, calculation_row, other_geo)
    _with_energy(database, calculation_row, geometry_row, -76.0)

    step = StepRow(
        stage1=StageRow(stationaries=[ref]), stage2=StageRow(stationaries=[other])
    )
    database.add(step)
    database.commit()

    text = export_mess_input(database, [step], ref=ref, model=calculation_row.model)

    assert "TODO(autostorage): no EnergyRow found" in text


def test__export_raises_on_missing_reference_energy(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that a missing reference energy raises rather than silently defaulting."""
    database.add(calculation_row)
    database.commit()

    ref = _stationary(database, calculation_row, geometry_row)
    other_geo = _diatomic(["H", "H"], 0.74)
    other = _stationary(database, calculation_row, other_geo)
    _with_energy(database, calculation_row, other_geo, -1.0)

    step = StepRow(
        stage1=StageRow(stationaries=[ref]), stage2=StageRow(stationaries=[other])
    )
    database.add(step)
    database.commit()

    with pytest.raises(ValueError, match="No EnergyRow found for reference"):
        export_mess_input(database, [step], ref=ref, model=calculation_row.model)


def test__export_fragment_order_deterministic(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that bimolecular fragments render in ascending-id order, not list order."""
    database.add(calculation_row)
    database.commit()

    ref = _stationary(database, calculation_row, geometry_row)
    _with_energy(database, calculation_row, geometry_row, -76.0)

    frag_a_geo = _diatomic(["C", "O"], 1.13)
    frag_b_geo = _diatomic(["H", "H"], 0.74)
    frag_a = _stationary(database, calculation_row, frag_a_geo)
    frag_b = _stationary(database, calculation_row, frag_b_geo)
    _with_energy(database, calculation_row, frag_a_geo, -10.0)
    _with_energy(database, calculation_row, frag_b_geo, -1.0)

    assert frag_a.id is not None
    assert frag_b.id is not None
    assert frag_a.id < frag_b.id

    bimolecular_stage = StageRow(stationaries=[frag_b, frag_a])
    step = StepRow(stage1=StageRow(stationaries=[ref]), stage2=bimolecular_stage)
    database.add(step)
    database.commit()

    text = export_mess_input(database, [step], ref=ref, model=calculation_row.model)

    assert text.index("Fragment  CO") < text.index("Fragment  H2")
