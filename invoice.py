# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta

__all__ = ['InvoiceLine']


class InvoiceLine(metaclass=PoolMeta):
    __name__ = 'account.invoice.line'
    working_shifts = fields.One2Many('working_shift', 'customer_invoice_line',
        'Working Shifts', readonly=True)
    interventions = fields.One2Many('working_shift.intervention',
        'customer_invoice_line', 'Interventions', readonly=True)

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        default = default.copy()
        default['working_shifts'] = None
        default['interventions'] = None
        return super(InvoiceLine, cls).copy(lines, default=default)
