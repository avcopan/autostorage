"""add geometry hash

Revision ID: 4230f63e365f
Revises: e50de3129c84
Create Date: 2026-07-23 19:58:37.026493

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes

from autostorage.models import _geometry_hash
from autostorage.types import CompressedArrayTypeDecorator


# revision identifiers, used by Alembic.
revision: str = '4230f63e365f'
down_revision: Union[str, Sequence[str], None] = 'e50de3129c84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Added nullable, backfilled per-row from existing `symbols`/`coordinates`/
    `charge`/`spin`, then tightened to NOT NULL + unique -- adding a NOT NULL
    unique column directly against a populated table isn't possible in one
    step. If the database already contains bit-identical duplicate geometries
    (only possible from before this constraint existed), the final
    `create_unique_constraint` below will fail; such rows must be
    deduplicated (and their foreign-key references remapped, as
    `autostorage.merge` does for a cross-database merge) before this
    migration can complete.
    """
    op.add_column(
        'geometry',
        sa.Column('geometry_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )

    bind = op.get_bind()
    decoder = CompressedArrayTypeDecorator()
    rows = bind.execute(
        sa.text('SELECT id, symbols, coordinates, charge, spin FROM geometry')
    ).fetchall()
    for row_id, symbols_json, coordinates_blob, charge, spin in rows:
        symbols = json.loads(symbols_json)
        coordinates = decoder.process_result_value(coordinates_blob, bind.dialect)
        geometry_hash = _geometry_hash(symbols, coordinates, charge, spin)
        bind.execute(
            sa.text('UPDATE geometry SET geometry_hash = :hash WHERE id = :id'),
            {'hash': geometry_hash, 'id': row_id},
        )

    # SQLite can't ALTER a column's nullability or add a constraint directly;
    # batch mode recreates the table under the hood.
    with op.batch_alter_table('geometry') as batch_op:
        batch_op.alter_column(
            'geometry_hash',
            existing_type=sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
        )
        batch_op.create_unique_constraint('unique_geometry_hash', ['geometry_hash'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('geometry') as batch_op:
        batch_op.drop_constraint('unique_geometry_hash', type_='unique')
        batch_op.drop_column('geometry_hash')
