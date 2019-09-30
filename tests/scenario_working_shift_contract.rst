===============================
Working Shift Contract Scenario
===============================

Imports::

    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from operator import attrgetter
    >>> from proteus import config, Model, Wizard
    >>> today = datetime.date.today()
    >>> now = datetime.datetime.now()
    >>> previous_month_first = (today - relativedelta(months=1)).replace(day=1)
    >>> previous_month_last = today.replace(day=1) - relativedelta(days=1)

Create database::

    >>> config = config.set_trytond()
    >>> config.pool.test = True

Install working_shift_contract::

    >>> Module = Model.get('ir.module.module')
    >>> module, = Module.find([('name', '=', 'working_shift_contract')])
    >>> module.click('install')
    >>> Wizard('ir.module.module.install_upgrade').execute('upgrade')

Create company::

    >>> Currency = Model.get('currency.currency')
    >>> CurrencyRate = Model.get('currency.currency.rate')
    >>> currencies = Currency.find([('code', '=', 'USD')])
    >>> if not currencies:
    ...     currency = Currency(name='U.S. Dollar', symbol='$', code='USD',
    ...         rounding=Decimal('0.01'), mon_grouping='[3, 3, 0]',
    ...         mon_decimal_point='.', mon_thousands_sep=',')
    ...     currency.save()
    ...     CurrencyRate(date=today + relativedelta(month=1, day=1),
    ...         rate=Decimal('1.0'), currency=currency).save()
    ... else:
    ...     currency, = currencies
    >>> Company = Model.get('company.company')
    >>> Party = Model.get('party.party')
    >>> company_config = Wizard('company.company.config')
    >>> company_config.execute('company')
    >>> company = company_config.form
    >>> party = Party(name='Dunder Mifflin')
    >>> party.save()
    >>> company.party = party
    >>> company.currency = currency
    >>> company_config.execute('add')
    >>> company, = Company.find([])

Reload the context::

    >>> User = Model.get('res.user')
    >>> Group = Model.get('res.group')
    >>> config._context = User.get_preferences(True, config.context)

Create fiscal year::

    >>> FiscalYear = Model.get('account.fiscalyear')
    >>> Sequence = Model.get('ir.sequence')
    >>> SequenceStrict = Model.get('ir.sequence.strict')
    >>> fiscalyear = FiscalYear(name=str(today.year))
    >>> fiscalyear.start_date = today + relativedelta(month=1, day=1)
    >>> fiscalyear.end_date = today + relativedelta(month=12, day=31)
    >>> fiscalyear.company = company
    >>> post_move_seq = Sequence(name=str(today.year), code='account.move',
    ...     company=company)
    >>> post_move_seq.save()
    >>> fiscalyear.post_move_sequence = post_move_seq
    >>> invoice_seq = SequenceStrict(name=str(today.year),
    ...     code='account.invoice', company=company)
    >>> invoice_seq.save()
    >>> fiscalyear.out_invoice_sequence = invoice_seq
    >>> fiscalyear.in_invoice_sequence = invoice_seq
    >>> fiscalyear.out_credit_note_sequence = invoice_seq
    >>> fiscalyear.in_credit_note_sequence = invoice_seq
    >>> fiscalyear.save()
    >>> FiscalYear.create_period([fiscalyear.id], config.context)

Create chart of accounts::

    >>> AccountTemplate = Model.get('account.account.template')
    >>> Account = Model.get('account.account')
    >>> Journal = Model.get('account.journal')
    >>> account_template, = AccountTemplate.find([('parent', '=', None)])
    >>> create_chart = Wizard('account.create_chart')
    >>> create_chart.execute('account')
    >>> create_chart.form.account_template = account_template
    >>> create_chart.form.company = company
    >>> create_chart.execute('create_account')
    >>> receivable, = Account.find([
    ...         ('kind', '=', 'receivable'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> payable, = Account.find([
    ...         ('kind', '=', 'payable'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> revenue, = Account.find([
    ...         ('kind', '=', 'revenue'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> expense, = Account.find([
    ...         ('kind', '=', 'expense'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> create_chart.form.account_receivable = receivable
    >>> create_chart.form.account_payable = payable
    >>> create_chart.execute('create_properties')
    >>> cash, = Account.find([
    ...         ('kind', '=', 'other'),
    ...         ('name', '=', 'Main Cash'),
    ...         ('company', '=', company.id),
    ...         ])
    >>> cash_journal, = Journal.find([('type', '=', 'cash')])
    >>> cash_journal.credit_account = cash
    >>> cash_journal.debit_account = cash
    >>> cash_journal.save()

Create payment term::

    >>> PaymentTerm = Model.get('account.invoice.payment_term')
    >>> PaymentTermLine = Model.get('account.invoice.payment_term.line')
    >>> payment_term = PaymentTerm(name='Direct')
    >>> payment_term_line = PaymentTermLine(type='remainder', days=0)
    >>> payment_term.lines.append(payment_term_line)
    >>> payment_term.save()

Create parties::

    >>> Party = Model.get('party.party')
    >>> customer1 = Party(name='Customer 1')
    >>> customer1.customer_payment_term = payment_term
    >>> customer1.save()
    >>> customer2 = Party(name='Customer2')
    >>> customer2.customer_payment_term = payment_term
    >>> customer2.save()

Create products::

    >>> ProductUom = Model.get('product.uom')
    >>> unit, = ProductUom.find([('name', '=', 'Unit')])
    >>> ProductTemplate = Model.get('product.template')
    >>> template = ProductTemplate()
    >>> template.name = 'Short Module'
    >>> template.default_uom = unit
    >>> template.type = 'service'
    >>> template.salable = True
    >>> template.list_price = Decimal('300')
    >>> template.cost_price = Decimal('300')
    >>> template.cost_price_method = 'fixed'
    >>> template.account_expense = expense
    >>> template.account_revenue = revenue
    >>> template.save()
    >>> service_short_module, = template.products
    >>> service_short_module.cost_price = Decimal('300')
    >>> service_short_module.save()

    >>> template = ProductTemplate()
    >>> template.name = 'Large Module'
    >>> template.default_uom = unit
    >>> template.type = 'service'
    >>> template.salable = True
    >>> template.list_price = Decimal('1000')
    >>> template.cost_price = Decimal('1000')
    >>> template.cost_price_method = 'fixed'
    >>> template.account_expense = expense
    >>> template.account_revenue = revenue
    >>> template.save()
    >>> service_large_module, = template.products
    >>> service_large_module.cost_price = Decimal('1000')
    >>> service_large_module.save()

    >>> template = ProductTemplate()
    >>> template.name = 'Intervention'
    >>> template.default_uom = unit
    >>> template.type = 'service'
    >>> template.salable = True
    >>> template.list_price = Decimal('300')
    >>> template.cost_price = Decimal('100')
    >>> template.cost_price_method = 'fixed'
    >>> template.account_expense = expense
    >>> template.account_revenue = revenue
    >>> template.save()
    >>> service_intervention, = template.products
    >>> service_intervention.cost_price = Decimal('100')
    >>> service_intervention.save()

Create Employees::

    >>> Employee = Model.get('company.employee')
    >>> employee_party = Party(name='Employee 1')
    >>> employee_party.save()
    >>> employee1 = Employee()
    >>> employee1.party = employee_party
    >>> employee1.company = company
    >>> employee1.save()
    >>> user, = User.find([])
    >>> user.employees.append(employee1)
    >>> user.employee = employee1
    >>> user.save()

    >>> employee_party = Party(name='Employee 2')
    >>> employee_party.save()
    >>> employee2 = Employee()
    >>> employee2.party = employee_party
    >>> employee2.company = company
    >>> employee2.save()

    >>> employee_party = Party(name='Employee 3')
    >>> employee_party.save()
    >>> employee3 = Employee()
    >>> employee3.party = employee_party
    >>> employee3.company = company
    >>> employee3.save()

    >>> config._context = User.get_preferences(True, config.context)

Configure sequences::

    >>> WorkingShiftConfig = Model.get('working_shift.configuration')
    >>> Sequence = Model.get('ir.sequence')
    >>> working_shift_config = WorkingShiftConfig(1)
    >>> intervention_sequence, = Sequence.find([
    ...     ('code', '=', 'working_shift.intervention')])
    >>> working_shift_config.intervention_sequence = intervention_sequence
    >>> working_shift_sequence, = Sequence.find([
    ...     ('code', '=', 'working_shift')])
    >>> working_shift_config.working_shift_sequence = working_shift_sequence
    >>> working_shift_config.save()

Create centers::
    >>> Center = Model.get('working_shift.center')
    >>> center1 = Center()
    >>> center1.name = 'Center 1'
    >>> center1.color = 'green'
    >>> center1.save()
    >>> center2 = Center()
    >>> center2.name = 'Center 2'
    >>> center2.color = 'yellow'
    >>> center2.save()

Create contracts::

    >>> Contract = Model.get('working_shift.contract')
    >>> contract_ws = Contract()
    >>> contract_ws.name = 'Invoice Working Shifts'
    >>> contract_ws.party = customer1
    >>> contract_ws.invoicing_method = 'working_shift'
    >>> contract_ws.requires_interventions = True
    >>> contract_ws.center = center1
    >>> contract_ws.start_time = datetime.time(8, 0)
    >>> contract_ws.end_time = datetime.time(11, 0)
    >>> rule = contract_ws.working_shift_rules.new()
    >>> rule.name = 'Rule 1'
    >>> rule.sequence = 1
    >>> rule.hours = 4.5
    >>> rule.product = service_short_module
    >>> rule.list_price
    Decimal('300')
    >>> rule = contract_ws.working_shift_rules.new()
    >>> rule.name = 'Rule 2'
    >>> rule.sequence = 2
    >>> rule.hours = 8
    >>> rule.product = service_large_module
    >>> rule.list_price
    Decimal('1000')
    >>> contract_ws.save()

    >>> contract_int = Contract()
    >>> contract_int.name = 'Invoice Interventions'
    >>> contract_int.party = customer2
    >>> contract_int.invoicing_method = 'intervention'
    >>> contract_int.requires_interventions
    True
    >>> contract_int.center = center2
    >>> contract_int.start_time = datetime.time(8, 0)
    >>> contract_int.end_time = datetime.time(11, 0)
    >>> rule = contract_int.intervention_rules.new()
    >>> rule.name = 'Rule 3'
    >>> rule.sequence = 1
    >>> rule.product = service_intervention
    >>> rule.list_price
    Decimal('300')
    >>> contract_int.save()

Create working shift checking constraint of required interventions::

    >>> Shift = Model.get('working_shift')
    >>> shift1 = Shift()
    >>> shift1.employee == employee1
    True
    >>> shift1.contract = contract_ws
    >>> shift1.date = today
    >>> shift1.start.date() == today
    True
    >>> shift1.start = datetime.datetime.combine(previous_month_first,
    ...     datetime.time(8, 0))
    >>> shift1.end = datetime.datetime.combine(previous_month_first,
    ...     datetime.time(11, 0))
    >>> shift1.hours
    Decimal('3.00')
    >>> shift1.save()
    >>> shift1.click('confirm')    # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UserError: ('UserError', (u'The field "Interventions" on "Working Shift" is required.', ''))

    >>> intervention = shift1.interventions.new()
    >>> intervention.start = shift1.start
    >>> intervention.end = shift1.start + relativedelta(hours=1)
    >>> shift1.save()
    >>> shift1.estimated_start.time() == contract_ws.start_time
    True
    >>> shift1.estimated_end.time() == contract_ws.end_time
    True
    >>> shift1.click('confirm')
    >>> shift1.click('done')

Create more working shifts::

    >>> shift2 = Shift()
    >>> shift2.employee == employee1
    True
    >>> shift2.contract = contract_ws
    >>> shift2.date = today
    >>> shift2.start = datetime.datetime.combine(previous_month_first,
    ...     datetime.time(12, 0))
    >>> shift2.end = datetime.datetime.combine(previous_month_first,
    ...     datetime.time(13, 0))
    >>> intervention = shift2.interventions.new()
    >>> intervention.start = shift2.start
    >>> intervention.end = shift2.start + relativedelta(hours=1)
    >>> shift2.click('confirm')
    >>> shift2.click('done')

    >>> shift_date = previous_month_first.replace(day=2)
    >>> shift3 = Shift()
    >>> shift3.date = today
    >>> shift3.employee = employee2
    >>> shift3.contract = contract_ws
    >>> shift3.start = datetime.datetime.combine(shift_date,
    ...     datetime.time(14, 0))
    >>> shift3.end = datetime.datetime.combine(shift_date,
    ...     datetime.time(21, 0))
    >>> intervention = shift3.interventions.new()
    >>> intervention.start = shift3.start
    >>> intervention.end = shift3.start + relativedelta(hours=1)
    >>> intervention = shift3.interventions.new()
    >>> intervention.start = shift3.start + relativedelta(hours=1.5)
    >>> intervention.end = shift3.start + relativedelta(hours=2)
    >>> shift3.click('confirm')
    >>> shift3.click('done')

    >>> shift4 = Shift()
    >>> shift4.date = today
    >>> shift4.employee == employee1
    True
    >>> shift4.contract = contract_int
    >>> shift4.start = datetime.datetime.combine(previous_month_first,
    ...     datetime.time(12, 0))
    >>> shift4.end = datetime.datetime.combine(previous_month_first,
    ...     datetime.time(13, 0))
    >>> intervention = shift4.interventions.new()
    >>> intervention.start = shift4.start
    >>> intervention.end = shift4.start + relativedelta(hours=1)
    >>> shift4.click('confirm') # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UserError: ...
    >>> shift4.contract.start_time = datetime.time(9, 30)
    >>> shift4.contract.end_time = datetime.time(10, 30)
    >>> shift4.contract.save()
    >>> shift4.click('confirm') # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UserError: ...
    >>> shift4.contract.start_time = datetime.time(7, 0)
    >>> shift4.contract.end_time = datetime.time(9, 0)
    >>> shift4.contract.save()
    >>> shift4.click('confirm') # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UserError: ...
    >>> shift4.contract.start_time = datetime.time(10, 0)
    >>> shift4.contract.end_time = datetime.time(12, 0)
    >>> shift4.contract.save()
    >>> shift4.click('confirm') # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UserError: ...
    >>> shift4.contract.start_time = datetime.time(7, 0)
    >>> shift4.contract.end_time = datetime.time(12, 0)
    >>> shift4.contract.save()
    >>> shift4.click('confirm') # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
        ...
    UserError: ...
    >>> shift4.contract.start_time = datetime.time(11, 0)
    >>> shift4.contract.end_time = datetime.time(13, 0)
    >>> shift4.contract.save()
    >>> shift4.employee = employee3
    >>> shift4.click('confirm')
    >>> shift4.click('done')
    >>> shift5 = Shift()
    >>> shift5.date = today
    >>> shift5.employee = employee2
    >>> shift5.contract = contract_int
    >>> shift5.start = datetime.datetime.combine(shift_date,
    ...     datetime.time(14, 0))
    >>> shift5.end = datetime.datetime.combine(shift_date,
    ...     datetime.time(21, 0))
    >>> intervention = shift5.interventions.new()
    >>> intervention.party = customer1
    >>> intervention.start = shift5.start
    >>> intervention.end = shift5.start + relativedelta(hours=1)
    >>> intervention = shift5.interventions.new()
    >>> intervention.start = shift5.start + relativedelta(hours=1.5)
    >>> intervention.end = shift5.start + relativedelta(hours=2)
    >>> shift5.click('confirm')
    >>> shift5.click('done')

Invoice customers::

    >>> invoice_customers = Wizard('working_shift.invoice_customers')
    >>> invoice_customers.form.start_date = previous_month_first
    >>> invoice_customers.form.end_date = today 
    >>> invoice_customers.execute('invoice')

Check working shift invoices::

    >>> Invoice = Model.get('account.invoice')
    >>> all(s.customer_invoice_line != None for s in [shift1, shift2, shift3])
    True
    >>> shift1.customer_invoice_line.invoice.party == customer1
    True
    >>> shift1.customer_invoice_line.product == service_short_module
    True
    >>> shift1.customer_invoice_line.quantity
    3.0
    >>> shift1.customer_invoice_line.amount
    Decimal('900.00')
    >>> shift2.customer_invoice_line == shift1.customer_invoice_line
    True
    >>> shift3.customer_invoice_line.invoice.party == customer1
    True
    >>> shift3.customer_invoice_line.product == service_short_module
    True
    >>> shift3.customer_invoice_line.quantity
    3.0
    >>> shift3.customer_invoice_line.amount
    Decimal('900.00')
    >>> [i.customer_invoice_line != None for s in [shift4, shift5]
    ...     for i in s.interventions]
    [True, True, True]
    >>> shift4_intervention = shift4.interventions[0]
    >>> shift5_intervention0 = shift5.interventions[0]
    >>> shift5_intervention1 = shift5.interventions[1]
    >>> shift4_intervention.customer_invoice_line.invoice.party == customer2
    True
    >>> shift4_intervention.customer_invoice_line.product == service_intervention
    True
    >>> shift4_intervention.customer_invoice_line.quantity
    2.0
    >>> shift4_intervention.customer_invoice_line.amount
    Decimal('600.00')
    >>> shift4_intervention.customer_invoice_line == shift5_intervention0.customer_invoice_line
    True
    >>> shift5_intervention1.customer_invoice_line.invoice.party == customer1
    True
    >>> shift5_intervention1.customer_invoice_line.product == service_intervention
    True
    >>> shift5_intervention1.customer_invoice_line.quantity
    1.0
    >>> shift5_intervention1.customer_invoice_line.amount
    Decimal('300.00')

    >>> customer1_invoice, = Invoice.find([('party', '=', customer1.id)])
    >>> len(customer1_invoice.lines)
    2
    >>> customer1_invoice.total_amount
    Decimal('1200.00')
    >>> customer2_invoice, = Invoice.find([('party', '=', customer2.id)])
    >>> len(customer2_invoice.lines)
    1
    >>> customer2_invoice.total_amount
    Decimal('600.00')
