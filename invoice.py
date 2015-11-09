# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta

__all__ = ['InvoiceLine']
__metaclass__ = PoolMeta


class InvoiceLine:
    __name__ = 'account.invoice.line'
    working_shifts = fields.One2Many('working_shift', 'customer_invoice_line',
        'Working Shifts', readonly=True)
    interventions = fields.One2Many('working_shift.intervention',
        'customer_invoice_line', 'Interventions', readonly=True)
