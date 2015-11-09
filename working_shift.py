# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from datetime import datetime, time
from dateutil.relativedelta import relativedelta

from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Or
from trytond.rpc import RPC
from trytond.wizard import Wizard, StateAction, StateView, Button

from trytond.modules.working_shift.working_shift import STATES, DEPENDS

__all__ = ['WorkingShift', 'Intervention',
    'WorkingShiftInvoiceCustomersDates', 'WorkingShiftInvoiceCustomers']
__metaclass__ = PoolMeta


class WorkingShift:
    __name__ = 'working_shift'
    contract = fields.Many2One('working_shift.contract', 'Contract',
        required=True, states=STATES, depends=DEPENDS)
    requires_interventions = fields.Function(fields.Boolean(
            'Requires Interventions'),
        'on_change_with_requires_interventions')
    customer_invoice_line = fields.Many2One('account.invoice.line',
        'Customer Invoice Line', readonly=True)
    customer_contract_rule = fields.Many2One(
        'working_shift.contract.working_shift_rule',
        'Customer Contract Rule', readonly=True)

    @classmethod
    def __setup__(cls):
        super(WorkingShift, cls).__setup__()
        interventions_states_clause = (Eval('state').in_(['confirmed', 'done'])
            & Eval('requires_interventions', False))
        if (cls.interventions.states
                and cls.interventions.states.get('required')):
            cls.interventions.states['required'] = Or(
                cls.interventions.states['required'],
                interventions_states_clause)
        else:
            if not cls.interventions.states:
                cls.interventions.states = {}
            cls.interventions.states['required'] = interventions_states_clause
        cls.interventions.depends.append('contract')

    @fields.depends('contract')
    def on_change_with_requires_interventions(self, name=None):
        return self.contract.requires_interventions if self.contract else False

    @classmethod
    def create_customer_invoices(cls, working_shifts):
        pool = Pool()
        Invoice = pool.get('account.invoice')

        invoice_lines_by_key = {}
        for working_shift in working_shifts:
            if working_shift.contract.invoicing_method == 'working_shift':
                key, invoice_line = (
                    working_shift.create_customer_invoice_line())
                if invoice_line:
                    invoice_lines_by_key.setdefault(key,
                        []).append(invoice_line)
            elif working_shift.contract.invoicing_method == 'intervention':
                for intervention in working_shift.interventions:
                    key, invoice_line = (
                        intervention.create_customer_invoice_line())
                    if invoice_line:
                        invoice_lines_by_key.setdefault(key,
                            []).append(invoice_line)

        invoices = []
        for invoice_key, invoice_lines in invoice_lines_by_key.iteritems():
            invoice = cls._get_invoice(invoice_key)
            if hasattr(invoice, 'lines'):
                invoice_lines = invoice.lines + invoice_lines
            invoice.lines = invoice_lines
            invoice.save()

            Invoice.update_taxes([invoice])
            invoices.append(invoice)
        return invoices

    def create_customer_invoice_line(self):
        assert self.contract.invoicing_method == 'working_shift'
        if self.customer_invoice_line:
            return None, None

        contract_rule = self._get_customer_contract_rule()
        invoice_line = self._get_customer_invoice_line(contract_rule)
        if invoice_line:
            invoice_line.save()
            self.customer_invoice_line = invoice_line
            self.customer_contract_rule = contract_rule
            self.save()

            key = ('out_invoice', self.contract.party)
            return key, invoice_line
        return None, None

    def _get_customer_contract_rule(self):
        assert self.contract.invoicing_method == 'working_shift'
        return self.contract.compute_matching_working_shift_rule(self)

    def _get_customer_invoice_line(self, contract_rule):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')

        assert self.contract.invoicing_method == 'working_shift'
        if not contract_rule:
            return

        invoice_line = InvoiceLine()
        invoice_line.invoice_type = 'out_invoice'
        invoice_line.party = self.contract.party
        invoice_line.type = 'line'
        invoice_line.description = contract_rule.product.rec_name  # TODO
        invoice_line.origin = self
        invoice_line.product = contract_rule.product
        invoice_line.unit_price = contract_rule.list_price
        invoice_line.quantity = 1.0
        invoice_line.unit = contract_rule.product.default_uom
        invoice_line.taxes = contract_rule.product.customer_taxes_used
        invoice_line.account = contract_rule.product.account_revenue_used
        if not invoice_line.account:
            self.raise_user_error('missing_account_revenue', {
                    'working_shift': self.rec_name,
                    'product': contract_rule.product.rec_name,
                    })
        return invoice_line

    @classmethod
    def _get_invoice(cls, invoice_key):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Journal = pool.get('account.journal')

        invoice_type = invoice_key[0]
        party = invoice_key[1]

        journal_type = ('revenue' if invoice_type == 'out_invoice'
            else 'expense')
        journals = Journal.search([
                ('type', '=', journal_type),
                ], limit=1)
        if journals:
            journal, = journals
        else:
            journal = None

        invoice_address = party.address_get(type='invoice')
        payment_term = party.customer_payment_term

        invoice = Invoice(
            type=invoice_type,
            journal=journal,
            party=party,
            invoice_address=invoice_address,
            account=party.account_receivable,
            payment_term=payment_term,
            )
        if hasattr(Invoice, 'payment_type'):
            invoice.payment_type = party.customer_payment_type
        return invoice


class Intervention:
    __name__ = 'working_shift.intervention'
    contract = fields.Function(fields.Many2One('working_shift.contract',
            'Contract'),
        'on_change_with_contract', searcher='search_contract')
    invoicing_method = fields.Function(fields.Selection(
            'get_invoicing_methods', 'Invoicing Method'),
        'on_change_with_invoicing_method', searcher='search_invoicing_method')
    customer_invoice_line = fields.Many2One('account.invoice.line',
        'Invoice Line', readonly=True)
    customer_contract_rule = fields.Many2One(
        'working_shift.contract.working_shift_rule',
        'Customer Contract Rule', readonly=True)

    @classmethod
    def __setup__(cls):
        super(Intervention, cls).__setup__()
        cls.__rpc__.update({
                'get_invoicing_methods': RPC(),
                })

        cls._error_messages.update({
                'missing_required_field_contract': ('The field "%(field)s" '
                    'of Working Shift Intervention "%(intervention)s" is '
                    'required because of the shift\'s contract.'),
                })

    @staticmethod
    def get_invoicing_methods():
        pool = Pool()
        Contract = pool.get('working_shift.contract')
        return Contract.invoicing_method.selection

    @fields.depends('shift', '_parent_shift.contract')
    def on_change_with_contract(self, name=None):
        if self.shift and self.shift.contract:
            return self.shift.contract.id

    @classmethod
    def search_contract(cls, name, clause):
        return [
            (('shift.contract',) + tuple(clause[1:])),
            ]

    @fields.depends('contract')
    def on_change_with_invoicing_method(self, name=None):
        pool = Pool()
        Contract = pool.get('working_shift.contract')
        if self.contract:
            return self.contract.invoicing_method
        return Contract.default_invoicing_method()

    @classmethod
    def search_invoicing_method(cls, name, clause):
        return [
            (('shift.contract.invoicing_method',) + tuple(clause[1:])),
            ]

    @classmethod
    def validate(cls, interventions):
        super(Intervention, cls).validate(interventions)
        cls.check_contract_fields(interventions)

    @classmethod
    def check_contract_fields(cls, interventions):
        interventions_by_contract = {}
        for intervention in interventions:
            interventions_by_contract.setdefault(intervention.shift.contract,
                []).append(intervention)
        for contract, contract_interventions \
                in interventions_by_contract.iteritems():
            cls._check_contract_fields(contract_interventions, contract)

    @classmethod
    def _check_contract_fields(cls, interventions, contract):
        required_fields = [cf.field for cf in contract.intervention_fields
            if cf.required]
        if not required_fields:
            return
        for intervention in interventions:
            for field in required_fields:
                if not getattr(intervention, field.name, None):
                    cls.raise_user_error('missing_required_field_contract', {
                            'intervention': intervention.rec_name,
                            'field': field.field_description,
                            })

    def create_customer_invoice_line(self):
        assert self.invoicing_method == 'intervention'
        if self.customer_invoice_line:
            return None, None

        contract_rule = self._get_customer_contract_rule()
        invoice_line = self._get_customer_invoice_line(contract_rule)
        if invoice_line:
            invoice_line.save()
            self.customer_invoice_line = invoice_line
            self.save()

            party = self.party if self.party else self.shift.contract.party
            key = ('out_invoice', party)
            return key, invoice_line
        return None, None

    def _get_customer_contract_rule(self):
        assert self.invoicing_method == 'intervention'
        contract = self.shift.contract
        return contract.compute_matching_intervention_rule(self)

    def _get_customer_invoice_line(self, contract_rule):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')

        assert self.invoicing_method == 'intervention'
        if not contract_rule:
            return

        invoice_line = InvoiceLine()
        invoice_line.invoice_type = 'out_invoice'
        invoice_line.party = (self.party if self.party
            else self.shift.contract.party)
        invoice_line.type = 'line'
        invoice_line.description = contract_rule.product.rec_name  # TODO
        invoice_line.origin = self
        invoice_line.product = contract_rule.product
        invoice_line.unit_price = contract_rule.list_price
        invoice_line.quantity = 1
        invoice_line.unit = contract_rule.product.default_uom
        invoice_line.taxes = contract_rule.product.customer_taxes_used
        invoice_line.account = contract_rule.product.account_revenue_used
        if not invoice_line.account:
            self.raise_user_error('missing_account_revenue', {
                    'intervention': self.rec_name,
                    'product': contract_rule.product.rec_name,
                    })
        return invoice_line


class WorkingShiftInvoiceCustomersDates(ModelView):
    'Working Shift Invoice Customers Dates'
    __name__ = 'working_shift.invoice_customers.dates'
    start_date = fields.Date('Start Date', required=True)
    end_date = fields.Date('End Date', required=True, domain=[
            ('end_date', '>=', Eval('start_date')),
            ], depends=['start_date'])


class WorkingShiftInvoiceCustomers(Wizard):
    'Working Shift Invoice Customers'
    __name__ = 'working_shift.invoice_customers'
    start_state = 'dates'
    dates = StateView('working_shift.invoice_customers.dates',
        'working_shift_contract.invoice_customers_dates_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Invoice', 'invoice', 'tryton-ok', default=True),
            ])
    invoice = StateAction('account_invoice.act_invoice_form')

    def do_invoice(self, action):
        pool = Pool()
        WorkingShift = pool.get('working_shift')

        shifts = WorkingShift.search([
                ('start_date', '>=',
                    datetime.combine(self.dates.start_date, time(0, 0, 0))),
                ('end_date', '<',
                    datetime.combine(
                        self.dates.end_date + relativedelta(days=1),
                        time(0, 0, 0))),
                ('state', '=', 'done'),
                ])
        if shifts:
            invoices = WorkingShift.create_customer_invoices(shifts)
            data = {'res_id': [i.id for i in invoices]}
            if len(invoices) == 1:
                action['views'].reverse()
        else:
            data = {'res_id': []}
        return action, data
