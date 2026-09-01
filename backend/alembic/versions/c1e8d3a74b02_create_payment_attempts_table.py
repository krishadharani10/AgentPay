"""create_payment_attempts_table

Revision ID: c1e8d3a74b02
Revises: b7c4e2f91a03
Create Date: 2026-08-31 23:42:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.models.base


# revision identifiers, used by Alembic.
revision: str = 'c1e8d3a74b02'
down_revision: Union[str, None] = 'b7c4e2f91a03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'payment_attempts',
        sa.Column('id', app.models.base.GUID(), nullable=False),
        sa.Column('transaction_id', app.models.base.GUID(), nullable=False),
        sa.Column('payment_method_id', app.models.base.GUID(), nullable=True),
        sa.Column('attempt_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='PENDING'),
        sa.Column('provider_payment_id', sa.String(length=255), nullable=True),
        sa.Column('error_code', sa.String(length=100), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('response_payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['payment_method_id'], ['payment_methods.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transaction_id', 'attempt_number', name='uq_payment_attempts_tx_attempt')
    )
    op.create_index(op.f('ix_payment_attempts_transaction_id'), 'payment_attempts', ['transaction_id'], unique=False)
    op.create_index(op.f('ix_payment_attempts_status'), 'payment_attempts', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_payment_attempts_status'), table_name='payment_attempts')
    op.drop_index(op.f('ix_payment_attempts_transaction_id'), table_name='payment_attempts')
    op.drop_table('payment_attempts')
