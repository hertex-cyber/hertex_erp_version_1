"""link processed payroll runs to their ledger postings

Revision ID: b19d4e63a870
Revises: a6c82d1f409b
Create Date: 2026-11-18 01:55:00.000000

"""
from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "b19d4e63a870"
down_revision: str | None = "a6c82d1f409b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hr_payroll_runs",
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_hr_payroll_runs_journal_entry_id",
        "hr_payroll_runs",
        "finance_journal_entries",
        ["journal_entry_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_hr_payroll_runs_journal_entry",
        "hr_payroll_runs",
        ["journal_entry_id"],
    )
    op.create_unique_constraint(
        "uq_hr_payroll_runs_tenant_period",
        "hr_payroll_runs",
        ["tenant_id", "period"],
    )
    connection = op.get_bind()
    tenant_ids = connection.execute(sa.text("SELECT id FROM tenants")).scalars().all()
    accounts = (
        ("5200", "Salaries", "expense"),
        ("2210", "Provident Fund Payable", "liability"),
        ("2220", "Employee State Insurance Payable", "liability"),
        ("2230", "Payroll TDS Payable", "liability"),
        ("2240", "Net Salaries Payable", "liability"),
    )
    params = [
        {
            "account_id": str(uuid4()),
            "code": code,
            "name": name,
            "account_type": account_type,
            "tenant_id": str(tenant_id),
        }
        for tenant_id in tenant_ids
        for code, name, account_type in accounts
    ]
    if params:
        connection.execute(
            sa.text(
                """
                INSERT INTO finance_accounts
                    (id, code, name, account_type, is_system, tenant_id, is_active)
                SELECT
                    CAST(:account_id AS uuid), :code, :name, :account_type,
                    FALSE, CAST(:tenant_id AS uuid), TRUE
                ON CONFLICT (tenant_id, code) DO NOTHING
                """
            ),
            params,
        )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM finance_accounts
            WHERE code IN ('2210', '2220', '2230', '2240')
              AND name IN (
                  'Provident Fund Payable',
                  'Employee State Insurance Payable',
                  'Payroll TDS Payable',
                  'Net Salaries Payable'
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM finance_journal_lines
                  WHERE finance_journal_lines.account_id = finance_accounts.id
              )
            """
        )
    )
    op.drop_constraint(
        "uq_hr_payroll_runs_tenant_period",
        "hr_payroll_runs",
        type_="unique",
    )
    op.drop_constraint(
        "uq_hr_payroll_runs_journal_entry",
        "hr_payroll_runs",
        type_="unique",
    )
    op.drop_constraint(
        "fk_hr_payroll_runs_journal_entry_id",
        "hr_payroll_runs",
        type_="foreignkey",
    )
    op.drop_column("hr_payroll_runs", "journal_entry_id")
