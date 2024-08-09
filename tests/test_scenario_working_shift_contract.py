import datetime
import unittest
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from proteus import Model, Wizard
from trytond.exceptions import UserError
from trytond.model.modelstorage import RequiredValidationError
from trytond.modules.account.tests.tools import (create_chart,
                                                 create_fiscalyear,
                                                 get_accounts)
from trytond.modules.account_invoice.tests.tools import (
    create_payment_term, set_fiscalyear_invoice_sequences)
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules, set_user


class Test(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):

        # Activate working_shift_contract
        activate_modules('working_shift_contract')

        # Create company
        _ = create_company()
        company = get_company()
        tax_identifier = company.party.identifiers.new()
        tax_identifier.type = 'eu_vat'
        tax_identifier.code = 'BE0897290877'
        company.party.save()

        # Create fiscal year
        fiscalyear = set_fiscalyear_invoice_sequences(
            create_fiscalyear(company))
        fiscalyear.click('create_period')

        # Create chart of accounts
        _ = create_chart(company)
        accounts = get_accounts(company)
        receivable = accounts['receivable']
        revenue = accounts['revenue']
        expense = accounts['expense']

        # Create payment term
        payment_term = create_payment_term()
        payment_term.save()

        # Create parties
        Party = Model.get('party.party')
        customer1 = Party(name='Customer 1')
        customer1.customer_payment_term = payment_term
        customer1.account_receivable = receivable
        customer1.save()
        customer2 = Party(name='Customer2')
        customer2.customer_payment_term = payment_term
        customer2.account_receivable = receivable
        customer2.save()

        # Create account category
        ProductCategory = Model.get('product.category')
        account_category = ProductCategory(name="Account Category")
        account_category.accounting = True
        account_category.account_expense = expense
        account_category.account_revenue = revenue
        account_category.save()

        # Create products
        ProductUom = Model.get('product.uom')
        unit, = ProductUom.find([('name', '=', 'Unit')])
        ProductTemplate = Model.get('product.template')
        template = ProductTemplate()
        template.name = 'Short Module'
        template.default_uom = unit
        template.type = 'service'
        template.list_price = Decimal('300')
        template.cost_price_method = 'fixed'
        template.account_category = account_category
        template.save()
        service_short_module, = template.products
        service_short_module.cost_price = Decimal('300')
        service_short_module.save()
        template = ProductTemplate()
        template.name = 'Large Module'
        template.default_uom = unit
        template.type = 'service'
        template.list_price = Decimal('1000')
        template.cost_price_method = 'fixed'
        template.account_category = account_category
        template.save()
        service_large_module, = template.products
        service_large_module.cost_price = Decimal('1000')
        service_large_module.save()
        template = ProductTemplate()
        template.name = 'Intervention'
        template.default_uom = unit
        template.type = 'service'
        template.list_price = Decimal('300')
        template.cost_price_method = 'fixed'
        template.account_category = account_category
        template.save()
        service_intervention, = template.products
        service_intervention.cost_price = Decimal('100')
        service_intervention.save()

        # Create Employees
        Employee = Model.get('company.employee')
        employee_party = Party(name='Employee 1')
        employee_party.save()
        employee1 = Employee()
        employee1.party = employee_party
        employee1.company = company
        employee1.save()
        User = Model.get('res.user')
        user, = User.find([])
        user.employees.append(employee1)
        user.employee = employee1
        user.save()
        employee_party = Party(name='Employee 2')
        employee_party.save()
        employee2 = Employee()
        employee2.party = employee_party
        employee2.company = company
        employee2.save()
        employee_party = Party(name='Employee 3')
        employee_party.save()
        employee3 = Employee()
        employee3.party = employee_party
        employee3.company = company
        employee3.save()
        set_user(user)

        # Configure sequences
        WorkingShiftConfig = Model.get('working_shift.configuration')
        Sequence = Model.get('ir.sequence')
        working_shift_config = WorkingShiftConfig(1)
        intervention_sequence, = Sequence.find([('sequence_type.name', '=',
                                                 'Working Shift Intervention')])
        working_shift_config.intervention_sequence = intervention_sequence
        working_shift_sequence, = Sequence.find([('sequence_type.name', '=',
                                                  'Working Shift')])
        working_shift_config.working_shift_sequence = working_shift_sequence
        working_shift_config.save()

        # Create centers
        Center = Model.get('working_shift.center')
        center1 = Center()
        center1.name = 'Center 1'
        center1.color = 'green'
        center1.save()
        center2 = Center()
        center2.name = 'Center 2'
        center2.color = 'yellow'
        center2.save()

        # Compute dates
        today = datetime.date.today()
        previous_month_first = (today - relativedelta(months=1)).replace(day=1)
        today.replace(day=1) - relativedelta(days=1)

        # Create contracts
        Contract = Model.get('working_shift.contract')
        contract_ws = Contract()
        contract_ws.name = 'Invoice Working Shifts'
        contract_ws.party = customer1
        contract_ws.invoicing_method = 'working_shift'
        contract_ws.requires_interventions = True
        contract_ws.center = center1
        contract_ws.start_time = datetime.time(8, 0)
        contract_ws.end_time = datetime.time(11, 0)
        rule = contract_ws.working_shift_rules.new()
        rule.name = 'Rule 1'
        rule.sequence = 1
        rule.hours = 4.5
        rule.product = service_short_module
        self.assertEqual(rule.list_price, Decimal('300'))
        rule = contract_ws.working_shift_rules.new()
        rule.name = 'Rule 2'
        rule.sequence = 2
        rule.hours = 8
        rule.product = service_large_module
        self.assertEqual(rule.list_price, Decimal('1000'))
        contract_ws.save()
        contract_int = Contract()
        contract_int.name = 'Invoice Interventions'
        contract_int.party = customer2
        contract_int.invoicing_method = 'intervention'
        self.assertEqual(contract_int.requires_interventions, True)
        contract_int.center = center2
        contract_int.start_time = datetime.time(8, 0)
        contract_int.end_time = datetime.time(11, 0)
        rule = contract_int.intervention_rules.new()
        rule.name = 'Rule 3'
        rule.sequence = 1
        rule.product = service_intervention
        self.assertEqual(rule.list_price, Decimal('300'))
        contract_int.save()

        # Create working shift checking constraint of required interventions
        Shift = Model.get('working_shift')
        shift1 = Shift()
        self.assertEqual(shift1.employee, employee1)
        shift1.contract = contract_ws
        shift1.date = today
        self.assertEqual(shift1.start.date(), today)
        shift1.start = datetime.datetime.combine(previous_month_first,
                                                 datetime.time(8, 0))
        shift1.end = datetime.datetime.combine(previous_month_first,
                                               datetime.time(11, 0))
        self.assertEqual(shift1.hours, Decimal('3.00'))
        shift1.save()
        with self.assertRaises(RequiredValidationError):
            shift1.click('confirm')
        intervention = shift1.interventions.new()
        intervention.start = shift1.start
        intervention.end = shift1.start + relativedelta(hours=1)
        shift1.save()
        self.assertEqual(shift1.estimated_start.time(), contract_ws.start_time)
        self.assertEqual(shift1.estimated_end.time(), contract_ws.end_time)
        shift1.click('confirm')
        shift1.click('done')

        # Create more working shifts
        shift2 = Shift()
        self.assertEqual(shift2.employee, employee1)
        shift2.contract = contract_ws
        shift2.date = today
        shift2.start = datetime.datetime.combine(previous_month_first,
                                                 datetime.time(12, 0))
        shift2.end = datetime.datetime.combine(previous_month_first,
                                               datetime.time(13, 0))
        intervention = shift2.interventions.new()
        intervention.start = shift2.start
        intervention.end = shift2.start + relativedelta(hours=1)
        shift2.click('confirm')
        shift2.click('done')
        shift_date = previous_month_first.replace(day=2)
        shift3 = Shift()
        shift3.date = today
        shift3.employee = employee2
        shift3.contract = contract_ws
        shift3.start = datetime.datetime.combine(shift_date,
                                                 datetime.time(14, 0))
        shift3.end = datetime.datetime.combine(shift_date, datetime.time(21, 0))
        intervention = shift3.interventions.new()
        intervention.start = shift3.start
        intervention.end = shift3.start + relativedelta(hours=1)
        intervention = shift3.interventions.new()
        intervention.start = shift3.start + relativedelta(hours=1.5)
        intervention.end = shift3.start + relativedelta(hours=2)
        shift3.click('confirm')
        shift3.click('done')
        shift4 = Shift()
        shift4.date = today
        self.assertEqual(shift4.employee, employee1)
        shift4.contract = contract_int
        shift4.start = datetime.datetime.combine(previous_month_first,
                                                 datetime.time(12, 0))
        shift4.end = datetime.datetime.combine(previous_month_first,
                                               datetime.time(13, 0))
        intervention = shift4.interventions.new()
        intervention.start = shift4.start
        intervention.end = shift4.start + relativedelta(hours=1)
        with self.assertRaises(UserError):
            shift4.click('confirm')
        shift4.contract.start_time = datetime.time(9, 30)
        shift4.contract.end_time = datetime.time(10, 30)
        shift4.contract.save()
        with self.assertRaises(UserError):
            shift4.click('confirm')
        shift4.contract.start_time = datetime.time(7, 0)
        shift4.contract.end_time = datetime.time(9, 0)
        shift4.contract.save()
        with self.assertRaises(UserError):
            shift4.click('confirm')
        shift4.contract.start_time = datetime.time(10, 0)
        shift4.contract.end_time = datetime.time(12, 0)
        shift4.contract.save()
        with self.assertRaises(UserError):
            shift4.click('confirm')
        shift4.contract.start_time = datetime.time(7, 0)
        shift4.contract.end_time = datetime.time(12, 0)
        shift4.contract.save()
        with self.assertRaises(UserError):
            shift4.click('confirm')
        shift4.contract.start_time = datetime.time(11, 0)
        shift4.contract.end_time = datetime.time(13, 0)
        shift4.contract.save()
        shift4.employee = employee3
        shift4.click('confirm')
        shift4.click('done')
        shift5 = Shift()
        shift5.date = today
        shift5.employee = employee2
        shift5.contract = contract_int
        shift5.start = datetime.datetime.combine(shift_date,
                                                 datetime.time(14, 0))
        shift5.end = datetime.datetime.combine(shift_date, datetime.time(21, 0))
        intervention = shift5.interventions.new()
        intervention.party = customer1
        intervention.start = shift5.start
        intervention.end = shift5.start + relativedelta(hours=1)
        intervention = shift5.interventions.new()
        intervention.start = shift5.start + relativedelta(hours=1.5)
        intervention.end = shift5.start + relativedelta(hours=2)
        shift5.click('confirm')
        shift5.click('done')

        # Invoice customers
        invoice_customers = Wizard('working_shift.invoice_customers')
        invoice_customers.form.start_date = previous_month_first
        invoice_customers.form.end_date = today
        invoice_customers.execute('invoice')

        # Check working shift invoices
        Invoice = Model.get('account.invoice')
        self.assertEqual(
            all(s.customer_invoice_line != None
                for s in [shift1, shift2, shift3]), True)
        self.assertEqual(shift1.customer_invoice_line.invoice.party, customer1)
        self.assertEqual(shift1.customer_invoice_line.product,
                         service_short_module)
        self.assertEqual(shift1.customer_invoice_line.quantity, 3.0)
        self.assertEqual(shift1.customer_invoice_line.amount, Decimal('900.00'))
        self.assertEqual(shift2.customer_invoice_line,
                         shift1.customer_invoice_line)
        self.assertEqual(shift3.customer_invoice_line.invoice.party, customer1)
        self.assertEqual(shift3.customer_invoice_line.product,
                         service_short_module)
        self.assertEqual(shift3.customer_invoice_line.quantity, 3.0)
        self.assertEqual(shift3.customer_invoice_line.amount, Decimal('900.00'))
        self.assertEqual([
            i.customer_invoice_line != None for s in [shift4, shift5]
            for i in s.interventions
        ], [True, True, True])
        shift4_intervention = shift4.interventions[0]
        shift5_intervention0 = shift5.interventions[0]
        shift5_intervention1 = shift5.interventions[1]
        self.assertEqual(
            shift4_intervention.customer_invoice_line.invoice.party, customer2)
        self.assertEqual(shift4_intervention.customer_invoice_line.product,
                         service_intervention)
        self.assertEqual(shift4_intervention.customer_invoice_line.quantity,
                         2.0)
        self.assertEqual(shift4_intervention.customer_invoice_line.amount,
                         Decimal('600.00'))
        self.assertEqual(shift4_intervention.customer_invoice_line,
                         shift5_intervention0.customer_invoice_line)
        self.assertEqual(
            shift5_intervention1.customer_invoice_line.invoice.party, customer1)
        self.assertEqual(shift5_intervention1.customer_invoice_line.product,
                         service_intervention)
        self.assertEqual(shift5_intervention1.customer_invoice_line.quantity,
                         1.0)
        self.assertEqual(shift5_intervention1.customer_invoice_line.amount,
                         Decimal('300.00'))
        customer1_invoice, = Invoice.find([('party', '=', customer1.id)])
        self.assertEqual(len(customer1_invoice.lines), 2)
        self.assertEqual(customer1_invoice.total_amount, Decimal('1200.00'))
        customer2_invoice, = Invoice.find([('party', '=', customer2.id)])
        self.assertEqual(len(customer2_invoice.lines), 1)
        self.assertEqual(customer2_invoice.total_amount, Decimal('600.00'))
