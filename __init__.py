# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import contract
from . import working_shift
from . import invoice


def register():
    Pool.register(
        contract.Contract,
        contract.WorkingShiftRule,
        contract.InterventionRule,
        contract.Field,
        contract.ContractField,
        working_shift.WorkingShift,
        working_shift.Intervention,
        working_shift.WorkingShiftInvoiceCustomersDates,
        invoice.InvoiceLine,
        module='working_shift_contract', type_='model')
    Pool.register(
        working_shift.WorkingShiftInvoiceCustomers,
        module='working_shift_contract', type_='wizard')
