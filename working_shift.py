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
        cls._error_messages.update({
                'invoiced_working_shift': ('You cannot cancel the working '
                    'shift "%s" because it is already invoiced.'),
                'invoiced_working_shift_interventions': (
                    'You cannot cancel the working shift "%s" because some of '
                    'its interventions are already invoiced.'),
                'missing_account_revenue': ('The product "%s" used to invoice '
                    'working shifts doesn\'t have Revenue Account.'),
                })

    @fields.depends('contract')
    def on_change_with_requires_interventions(self, name=None):
        return self.contract.requires_interventions if self.contract else False

    @classmethod
    def cancel(cls, working_shifts):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')

        for working_shift in working_shifts:
            working_shift.check_cancellable()

        super(WorkingShift, cls).cancel(working_shifts)

        inv_line_to_write = set()
        for working_shift in working_shifts:
            if working_shift.contract.invoicing_method == 'working_shift':
                if working_shift.customer_invoice_line:
                    working_shift.customer_invoice_line.quantity -= 1
                    inv_line_to_write.add(working_shift.customer_invoice_line)
            elif working_shift.contract.invoicing_method == 'intervention':
                for intervention in working_shift.interventions:
                    if intervention.customer_invoice_line:
                        intervention.customer_invoice_line.quantity -= 1
                        inv_line_to_write.add(
                            intervention.customer_invoice_line)
        if inv_line_to_write:
            to_write = []
            for invoice_line in inv_line_to_write:
                to_write.extend(([invoice_line], invoice_line._save_values))
            InvoiceLine.write(*to_write)

    def check_cancellable(self):
        if self.contract.invoicing_method == 'working_shift':
            if (self.customer_invoice_line
                    and self.customer_invoice_line.invoice
                    and self.customer_invoice_line.invoice.state
                    not in ('cancel', 'draft')):
                self.raise_user_error('invoiced_working_shift', self.rec_name)
        elif self.contract.invoicing_method == 'intervention':
            invoiced_interventions = [i for i in self.interventions
                if i.customer_invoice_line and i.customer_invoice_line.invoice
                and i.customer_invoice_line.state not in ('cancel', 'draft')]
            if invoiced_interventions:
                self.raise_user_error('invoiced_working_shift_interventions',
                    self.rec_name)

    @classmethod
    def create_customer_invoices(cls, working_shifts):
        pool = Pool()
        Intervention = pool.get('working_shift.intervention')
        Invoice = pool.get('account.invoice')

        party2working_shifts = {}
        party2interventions = {}
        for working_shift in working_shifts:
            if working_shift.contract.invoicing_method == 'working_shift':
                party2working_shifts.setdefault(
                    working_shift.contract.party, []).append(working_shift)
            elif working_shift.contract.invoicing_method == 'intervention':
                for intervention in working_shift.interventions:
                    party = (intervention.party if intervention.party
                        else intervention.shift.contract.party)
                    party2interventions.setdefault(
                        party, []).append(intervention)

        party2invoice_lines = {}
        for party, working_shifts_to_inv in party2working_shifts.iteritems():
            inv_lines = cls.create_customer_invoice_line(working_shifts_to_inv,
                party)
            if inv_lines:
                party2invoice_lines.setdefault(party, []).extend(inv_lines)

        for party, interventions_to_inv in party2interventions.iteritems():
            inv_lines = Intervention.create_customer_invoice_line(
                interventions_to_inv, party)
            if inv_lines:
                party2invoice_lines.setdefault(party, []).extend(inv_lines)

        invoices = []
        for party, invoice_lines in party2invoice_lines.iteritems():
            invoice = cls._get_invoice('out_invoice', party)
            if hasattr(invoice, 'lines'):
                invoice_lines = invoice.lines + tuple(invoice_lines)
            invoice.lines = invoice_lines
            invoice.save()

            Invoice.update_taxes([invoice])
            invoices.append(invoice)
        return invoices

    @classmethod
    def create_customer_invoice_line(cls, working_shifts, party):
        rule2working_shifts = {}
        for working_shift in working_shifts:
            assert working_shift.contract.invoicing_method == 'working_shift'
            if working_shift.customer_invoice_line:
                continue
            rule = working_shift._get_customer_contract_rule()
            rule2working_shifts.setdefault(rule, []).append(working_shift)

        inv_lines = []
        for rule, rule_working_shifts in rule2working_shifts.iteritems():
            invoice_line = cls._get_customer_invoice_line(rule, party,
                len(rule_working_shifts))
            if invoice_line:
                invoice_line.save()
                cls.write(rule_working_shifts, {
                        'customer_invoice_line': invoice_line.id,
                        'customer_contract_rule': rule.id,
                        })
                inv_lines.append(invoice_line)
        return inv_lines

    def _get_customer_contract_rule(self):
        assert self.contract.invoicing_method == 'working_shift'
        return self.contract.compute_matching_working_shift_rule(self)

    @classmethod
    def _get_customer_invoice_line(cls, contract_rule, party, quantity):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')

        if not contract_rule:
            return
        assert contract_rule.contract.invoicing_method == 'working_shift'
        if not contract_rule.product.account_revenue_used:
            cls.raise_user_error('missing_account_revenue',
                contract_rule.product.rec_name)

        invoice_line = InvoiceLine()
        invoice_line.invoice_type = 'out_invoice'
        invoice_line.party = party
        invoice_line.type = 'line'
        invoice_line.description = '%s - %s' % (contract_rule.contract.name,
            contract_rule.name)
        invoice_line.product = contract_rule.product
        invoice_line.unit_price = contract_rule.list_price
        invoice_line.quantity = quantity
        invoice_line.unit = contract_rule.product.default_uom
        invoice_line.taxes = contract_rule.product.customer_taxes_used
        invoice_line.account = contract_rule.product.account_revenue_used
        return invoice_line

    @classmethod
    def _get_invoice(cls, invoice_type, party):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Journal = pool.get('account.journal')

        invoices = Invoice.search([
                ('type', '=', invoice_type),
                ('party', '=', party.id),
                ])
        if invoices:
            return invoices[0]

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
            if invoice_type in ('out_invoice', 'out_credit_note'):
                invoice.payment_type = party.customer_payment_type
            else:
                invoice.payment_type = party.supplier_payment_type
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
                'missing_account_revenue': ('The product "%s" used to invoice '
                    'interventions doesn\'t have Revenue Account.'),
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

    @classmethod
    def create_customer_invoice_line(cls, interventions, party):
        rule2interventions = {}
        for intervention in interventions:
            assert intervention.invoicing_method == 'intervention'
            if intervention.customer_invoice_line:
                continue
            rule = intervention._get_customer_contract_rule()
            rule2interventions.setdefault(rule, []).append(intervention)

        inv_lines = []
        for rule, rule_interventions in rule2interventions.iteritems():
            invoice_line = cls._get_customer_invoice_line(rule, party,
                len(rule_interventions))
            if invoice_line:
                invoice_line.save()
                cls.write(rule_interventions, {
                        'customer_invoice_line': invoice_line.id,
                        'customer_contract_rule': rule.id,
                        })
                inv_lines.append(invoice_line)
        return inv_lines

    def _get_customer_contract_rule(self):
        assert self.invoicing_method == 'intervention'
        contract = self.shift.contract
        return contract.compute_matching_intervention_rule(self)

    @classmethod
    def _get_customer_invoice_line(cls, contract_rule, party, quantity):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')

        if not contract_rule:
            return
        assert contract_rule.contract.invoicing_method == 'intervention'
        if not contract_rule.product.account_revenue_used:
            cls.raise_user_error('missing_account_revenue',
                contract_rule.product.rec_name)

        invoice_line = InvoiceLine()
        invoice_line.invoice_type = 'out_invoice'
        invoice_line.party = party
        invoice_line.type = 'line'
        invoice_line.description = '%s - %s' % (contract_rule.contract.name,
            contract_rule.name)
        invoice_line.product = contract_rule.product
        invoice_line.unit_price = contract_rule.list_price
        invoice_line.quantity = quantity
        invoice_line.unit = contract_rule.product.default_uom
        invoice_line.taxes = contract_rule.product.customer_taxes_used
        invoice_line.account = contract_rule.product.account_revenue_used
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
                ('start_date', '<',
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
