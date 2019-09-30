# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import contract
from . import center
from . import working_shift
from . import invoice


def register():
    Pool.register(
        center.Center,
        contract.Contract,
        contract.ContractField,
        contract.Field,
        contract.InterventionRule,
        contract.WorkingShiftRule,
        working_shift.Intervention,
        working_shift.WorkingShift,
        working_shift.WorkingShiftInvoiceCustomersDates,
        invoice.InvoiceLine,
        module='working_shift_contract', type_='model')
    Pool.register(
        working_shift.WorkingShiftInvoiceCustomers,
        module='working_shift_contract', type_='wizard')
