# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .contract import *
from .working_shift import *
from .invoice import *


def register():
    Pool.register(
        Contract,
        WorkingShiftRule,
        InterventionRule,
        Field,
        ContractField,
        WorkingShift,
        Intervention,
        WorkingShiftInvoiceCustomersDates,
        InvoiceLine,
        module='working_shift_contract', type_='model')
    Pool.register(
        WorkingShiftInvoiceCustomers,
        module='working_shift_contract', type_='wizard')
