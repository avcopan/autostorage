"""Autostorage PES plot tests."""

from pathlib import Path

import numpy as np
import pytest
from matplotlib.axes import Axes
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from autostorage import CalculationRow, Database, GeometryRow, StageRow, StepRow
from autostorage.utils import PESPlot, plot_pes
from tests.test_utils import _diatomic, _stationary, _with_energy

PNG_MAGIC_BYTES = b"\x89PNG\r\n\x1a\n"

EXPECTED_TS_PATH_LINE_COUNT = 5  # 3 levels + 2 connectors
EXPECTED_TS_PATH_TEXT_COUNT = 3  # 2 species + 1 TS peak
EXPECTED_BARRIERLESS_LINE_COUNT = 3  # 2 levels + 1 connector


def _new_figure_and_axes() -> tuple[Figure, Axes]:
    """Build a bare Figure/Axes without touching pyplot's global state."""
    figure = Figure()
    FigureCanvasAgg(figure)
    return figure, figure.add_subplot()


def test__plot_normal_path_with_ts(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that a well + bimolecular + barrier network draws all segments."""
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

    result = plot_pes(database, [step], ref=ref, model=calculation_row.model)

    assert isinstance(result, PESPlot)
    assert isinstance(result.figure, Figure)
    assert isinstance(result.axes, Axes)
    assert len(result.axes.lines) == EXPECTED_TS_PATH_LINE_COUNT
    assert len(result.axes.texts) == EXPECTED_TS_PATH_TEXT_COUNT
    assert any(t.get_text().startswith("B1") for t in result.axes.texts)


def test__plot_barrierless_step(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that a barrierless step draws a dashed connector, no TS peak."""
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

    result = plot_pes(database, [step], ref=ref, model=calculation_row.model)

    assert len(result.axes.lines) == EXPECTED_BARRIERLESS_LINE_COUNT
    connector = result.axes.lines[-1]
    assert connector.get_linestyle() == "--"
    assert any(t.get_text() == "B1" for t in result.axes.texts)


def test__plot_missing_energy_flagged(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that a species missing an EnergyRow is flagged, not raised."""
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

    result = plot_pes(database, [step], ref=ref, model=calculation_row.model)

    flagged_lines = [line for line in result.axes.lines if line.get_linestyle() == "--"]
    assert any(np.asarray(line.get_ydata())[0] == 0.0 for line in flagged_lines)
    assert any(t.get_text().endswith("(no energy data)") for t in result.axes.texts)


def test__plot_repr_png_returns_valid_png(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that _repr_png_ returns bytes recognizable as a PNG (Jupyter hook)."""
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

    result = plot_pes(database, [step], ref=ref, model=calculation_row.model)
    png = result._repr_png_()

    assert isinstance(png, bytes)
    assert png.startswith(PNG_MAGIC_BYTES)


def test__plot_save_writes_png(
    database: Database,
    calculation_row: CalculationRow,
    geometry_row: GeometryRow,
    tmp_path: Path,
) -> None:
    """Test that save() writes a real PNG file, inferring format from suffix."""
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

    result = plot_pes(database, [step], ref=ref, model=calculation_row.model)
    path = tmp_path / "pes.png"
    result.save(path)

    assert path.exists()
    assert path.read_bytes()[:8] == PNG_MAGIC_BYTES


def test__plot_save_writes_svg(
    database: Database,
    calculation_row: CalculationRow,
    geometry_row: GeometryRow,
    tmp_path: Path,
) -> None:
    """Test that save() writes a real SVG file, inferring format from suffix."""
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

    result = plot_pes(database, [step], ref=ref, model=calculation_row.model)
    path = tmp_path / "pes.svg"
    result.save(path)

    assert path.exists()
    assert "<svg" in path.read_text()


def test__plot_ax_parameter_draws_into_supplied_axes(
    database: Database, calculation_row: CalculationRow, geometry_row: GeometryRow
) -> None:
    """Test that a caller-supplied Axes is drawn into and returned as-is."""
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

    figure, axes = _new_figure_and_axes()
    result = plot_pes(database, [step], ref=ref, model=calculation_row.model, ax=axes)

    assert result.axes is axes
    assert result.figure is figure


def test__plot_raises_on_missing_reference_energy(
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
        plot_pes(database, [step], ref=ref, model=calculation_row.model)
