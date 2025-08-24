"""create helpful indices

Revision ID: 20250824_0001
Revises:
Create Date: 2025-08-24 00:00:00

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "20250824_0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Nota: SQLModel por defecto usa nombres de tabla "shoppingitem", "planentry", "kvcache"
    try:
        op.create_index("ix_shoppingitem_user_name", "shoppingitem", ["user_id", "name"], unique=False)
    except Exception:
        pass
    try:
        op.create_index("ix_planentry_user_date", "planentry", ["user_id", "plan_date"], unique=False)
    except Exception:
        pass
    try:
        op.create_index("ix_kvcache_user_key", "kvcache", ["user_id", "key"], unique=False)
    except Exception:
        pass

def downgrade():
    try:
        op.drop_index("ix_shoppingitem_user_name", table_name="shoppingitem")
    except Exception:
        pass
    try:
        op.drop_index("ix_planentry_user_date", table_name="planentry")
    except Exception:
        pass
    try:
        op.drop_index("ix_kvcache_user_key", table_name="kvcache")
    except Exception:
        pass
