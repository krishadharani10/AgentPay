"""update_transaction_status_default_to_requested

Revision ID: b7c4e2f91a03
Revises: aa0debb3d340
Create Date: 2026-08-31 23:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c4e2f91a03'
down_revision: Union[str, None] = 'aa0debb3d340'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update the Python-side default for transactions.status column
    # from 'PENDING' to 'REQUESTED' (TransactionStatus.REQUESTED.value).
    # Also migrate any existing rows with status='PENDING' to 'PAYMENT_PENDING'
    # since 'PENDING' is no longer a valid TransactionStatus value.
    op.execute(
        sa.text("UPDATE transactions SET status = 'PAYMENT_PENDING' WHERE status = 'PENDING'")
    )


def downgrade() -> None:
    # Revert 'PAYMENT_PENDING' back to 'PENDING' for backward compatibility.
    op.execute(
        sa.text("UPDATE transactions SET status = 'PENDING' WHERE status = 'PAYMENT_PENDING'")
    )
