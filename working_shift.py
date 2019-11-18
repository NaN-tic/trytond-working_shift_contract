# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from datetime import datetime, time, timedelta
from dateutil.relativedelta import relativedelta
from trytond import backend
from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Or, Bool
from trytond.rpc import RPC
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateAction, StateView, Button
from trytond.i18n import gettext
from trytond.exceptions import UserError
from trytond.modules.working_shift.working_shift import STATES, DEPENDS
from decimal import Decimal
import pytz

__all__ = ['WorkingShift', 'Intervention',
    'WorkingShiftInvoiceCustomersDates', 'WorkingShiftInvoiceCustomers']


class WorkingShift(metaclass=PoolMeta):
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
    date = fields.Date('Date', required=True)
    estimated_start = fields.DateTime('Estimated Start', required=True,
        states=STATES, depends=DEPENDS)
    estimated_end = fields.DateTime('Estimated End',
        domain=[
            ['OR',
                ('estimated_end', '=', None),
                ('estimated_end', '>', Eval('estimated_start')),
                ],
            ],
        states={
            'required': Eval('state').in_(['confirmed', 'done']),
            }, depends=(DEPENDS + ['estimated_start']))
    estimated_hours = fields.Function(fields.Numeric('Estimated Hours',
            digits=(16, 2)), 'on_change_with_estimated_hours')

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

        if cls.start.states:
            if cls.start.states.get('readonly'):
                cls.start.states['readonly'] |= Bool(Eval('end'))
            else:
                cls.start.states['readonly'] = Bool(Eval('end'))
        else:
            cls.start.states = {}
            cls.start.states['readonly'] = Bool(Eval('end'))

        if cls.end.states:
            if cls.end.states.get('readonly'):
                cls.end.states['readonly'] |= Bool(Eval('end'))
            else:
                cls.end.states['readonly'] = Bool(Eval('end'))
        else:
            cls.end.states = {}
            cls.end.states['readonly'] = Bool(Eval('end'))

    @classmethod
    def validate(cls, records):
        super(WorkingShift, cls).validate(records)
        for record in records:
            record.check_employee()

    def check_employee(self):
        pool = Pool()
        WorkingShift = pool.get('working_shift')

        if self.employee and self.estimated_start and self.estimated_end:

            clause = [
                ('employee', '=', self.employee),
                ('date', '=', self.date),
                ('contract.center', '!=', self.contract.center),
                ['OR',
                    [
                        ('estimated_start', '>=', self.estimated_start),
                        ('estimated_start', '<', self.estimated_end),
                    ], [
                        ('estimated_start', '<=', self.estimated_start),
                        ('estimated_end', '>=', self.estimated_end),
                    ], [
                        ('estimated_end', '>', self.estimated_start),
                        ('estimated_end', '<=', self.estimated_end),
                    ],
                ],
            ]

            conflicts = WorkingShift.search(clause)
            if conflicts:
                module = 'working_shift_contract'
                msg_id = 'employee_also_in_working_shift'
                raise UserError(gettext(
                        '{}.{}'.format(module, msg_id),
                        employee=self.employee.rec_name,
                        working_shift=self.rec_name,
                        conflictive_working_shift=conflicts[0].rec_name))

    @staticmethod
    def default_date():
        return datetime.today().date()

    def get_estimated_datetime(self, name):
        pool = Pool()
        User = pool.get('res.user')
        user = User(Transaction().user)
        # If the user's company has a defined timezone, the datetime widget
        # shows the time with the offset of the applied timezone, this is
        # why we must eliminate the offset if we do not want it to be
        # applied again by the tryton client.
        # See:
        # http://docs.tryton.org/projects/server/en/5.2/ref/models/fields.html#datetime
        timezone = None
        if user.company.timezone:
            timezone = pytz.timezone(user.company.timezone)

        time = getattr(self.contract, '%s_time' % name)
        if time:
            result = datetime.combine(self.date, time)
            if timezone:
                offset = timezone.utcoffset(result)
                result -= offset
            return result

    @fields.depends('contract', 'date')
    def on_change_date(self, name=None):
        if not self.contract or not self.date:
            self.estimated_start = None
            self.estimated_end = None
        else:
            self.estimated_start = self.get_estimated_datetime('start')
            self.estimated_end = self.get_estimated_datetime('end')
            if self.estimated_end <= self.estimated_start:
                self.estimated_end += timedelta(days=1)

    @fields.depends(methods=['on_change_date'])
    def on_change_contract(self, name=None):
        self.on_change_date()

    @fields.depends('estimated_start', 'estimated_end')
    def on_change_with_estimated_hours(self, name=None):
        if not self.estimated_start or not self.estimated_end:
            return Decimal(0)
        estimated_hours = ((self.estimated_end -
                self.estimated_start).total_seconds() / 3600.0)
        digits = self.__class__.estimated_hours.digits
        return Decimal(str(estimated_hours)).quantize(
            Decimal(str(10 ** -digits[1])))

    @fields.depends('contract')
    def on_change_with_requires_interventions(self, name=None):
        return self.contract.requires_interventions if self.contract else False

    @classmethod
    def cancel(cls, working_shifts):
        for working_shift in working_shifts:
            working_shift.check_cancellable()

        super(WorkingShift, cls).cancel(working_shifts)

        cls.write(working_shifts, {
            'customer_invoice_line': None,
            'customer_contract_rule': None,
            })

    def check_cancellable(self):
        if self.contract.invoicing_method == 'working_shift':
            if self.customer_invoice_line:
                raise UserError(gettext(
                    'working_shift_contract.invoiced_working_shift',
                    ws=self.rec_name))
        elif self.contract.invoicing_method == 'intervention':
            for intervention in self.interventions:
                if intervention.customer_invoice_line:
                    module = 'working_shift_contract'
                    msg_id = 'invoiced_working_shift_interventions'
                    raise UserError(gettext(
                        '{}.{}'.format(module, msg_id),
                        ws=self.rec_name))

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
        for party, working_shifts_to_inv in list(party2working_shifts.items()):
            inv_lines = cls.create_customer_invoice_line(working_shifts_to_inv,
                party)
            if inv_lines:
                party2invoice_lines.setdefault(party, []).extend(inv_lines)

        for party, interventions_to_inv in list(party2interventions.items()):
            inv_lines = Intervention.create_customer_invoice_line(
                interventions_to_inv, party)
            if inv_lines:
                party2invoice_lines.setdefault(party, []).extend(inv_lines)

        invoices = []
        for party, invoice_lines in list(party2invoice_lines.items()):
            invoice = cls._get_invoice('out', party)
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
        for rule, rule_working_shifts in list(rule2working_shifts.items()):
            invoice_line = cls._get_customer_invoice_line(rule, party,
                rule_working_shifts)
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
    def _get_customer_invoice_line(cls, contract_rule, party, working_shifts):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')
        Tax = pool.get('account.tax')

        if not contract_rule:
            return
        assert contract_rule.contract.invoicing_method == 'working_shift'
        if not contract_rule.product.account_revenue_used:
            raise UserError(gettext(
                'working_shift_contract.missing_account_revenue',
                product=contract_rule.product.rec_name))

        invoice_line = InvoiceLine()
        invoice_line.invoice_type = 'out'
        invoice_line.party = party
        invoice_line.type = 'line'
        invoice_line.description = '%s - %s' % (contract_rule.contract.name,
            contract_rule.name)
        invoice_line.product = contract_rule.product
        invoice_line.unit_price = contract_rule.list_price
        invoice_line.quantity = \
            cls._get_customer_invoice_line_quantity(contract_rule, working_shifts)
        invoice_line.unit = contract_rule.product.default_uom
        invoice_line.account = contract_rule.product.account_revenue_used

        invoice_line.taxes = []
        pattern = invoice_line._get_tax_rule_pattern()
        for tax in contract_rule.product.customer_taxes_used:
            if party.customer_tax_rule:
                tax_ids = party.customer_tax_rule.apply(tax, pattern)
                if tax_ids:
                    invoice_line.taxes.extend(Tax.browse(tax_ids))
                continue
            invoice_line.taxes.append(tax)
        if party.customer_tax_rule:
            tax_ids = party.customer_tax_rule.apply(None, pattern)
            if tax_ids:
                invoice_line.taxes.extend(Tax.browse(tax_ids))

        return invoice_line

    @classmethod
    def _get_customer_invoice_line_quantity(cls, contract_rule, working_shifts):
        return len(working_shifts)

    @classmethod
    def _get_invoice(cls, invoice_type, party):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Journal = pool.get('account.journal')

        invoices = Invoice.search([
                ('type', '=', invoice_type),
                ('party', '=', party.id),
                ('state', '=', 'draft'),
                ])
        if invoices:
            return invoices[0]

        journal_type = ('revenue' if invoice_type == 'out'
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
            if invoice_type == 'out':
                invoice.payment_type = party.customer_payment_type
            else:
                invoice.payment_type = party.supplier_payment_type
        return invoice

    @classmethod
    def copy(cls, working_shifts, default=None):
        if default is None:
            default = {}
        default = default.copy()
        default['customer_invoice_line'] = None
        default['customer_contract_rule'] = None
        default['state'] = 'draft'
        return super(WorkingShift, cls).copy(working_shifts, default=default)


class Intervention(metaclass=PoolMeta):
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
        'working_shift.contract.intervention_rule',
        'Customer Contract Rule', readonly=True)

    @classmethod
    def __setup__(cls):
        super(Intervention, cls).__setup__()
        cls.__rpc__.update({
                'get_invoicing_methods': RPC(),
                })

    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')

        # Migration from 3.4.0: remove invalid foreign key
        table = TableHandler(cls, module_name)
        table.drop_fk('customer_contract_rule')

        super(Intervention, cls).__register__(module_name)

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
                in list(interventions_by_contract.items()):
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
                    module = 'working_shift_contract'
                    msg_id = 'missing_required_field_contract'
                    raise UserError(gettext(
                            '{}.{}'.format(module, msg_id),
                            intervention=intervention.rec_name,
                            field=field.field_description))

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
        for rule, rule_interventions in list(rule2interventions.items()):
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
            raise UserError(gettext(
                'working_shift_contract.missing_account_revenue',
                contract=contract_rule.product.rec_name))

        invoice_line = InvoiceLine()
        invoice_line.invoice_type = 'out'
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
    def copy(cls, interventions, default=None):
        if default is None:
            default = {}
        default = default.copy()
        default['customer_invoice_line'] = None
        default['customer_contract_rule'] = None
        return super(Intervention, cls).copy(interventions, default=default)


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
    invoice = StateAction('account_invoice.act_invoice_out_form')

    def do_invoice(self, action):
        pool = Pool()
        WorkingShift = pool.get('working_shift')

        shifts = WorkingShift.search([
                ('date', '>=',
                    datetime.combine(self.dates.start_date, time(0, 0, 0))),
                ('date', '<',
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
