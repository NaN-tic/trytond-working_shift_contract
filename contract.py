# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.config import config
from trytond.model import ModelSQL, ModelView, MatchMixin, fields
from trytond.pyson import Eval, Id, If
from trytond.pool import PoolMeta
DIGITS = config.getint('digits', 'unit_price_digits', 4)

__all__ = ['Contract', 'WorkingShiftRule', 'InterventionRule', 'Field',
    'ContractField']
__metaclass__ = PoolMeta


class Contract(ModelSQL, ModelView):
    'Working Shift Contract'
    __name__ = 'working_shift.contract'
    name = fields.Char('Name', required=True)
    party = fields.Many2One('party.party', 'Party', required=True)
    invoicing_method = fields.Selection([
            ('working_shift', 'Working Shifts'),
            ('intervention', 'Interventions'),
            ], 'Invoicing Method', required=True)
    requires_interventions = fields.Boolean('Requires Interventions', domain=[
            If(Eval('invoicing_method') == 'intervention',
                ('requires_interventions', '=', True),
                ()),
            ],
        states={
            'readonly': Eval('invoicing_method') == 'intervention',
            }, depends=['invoicing_method'],
        help='A Working Shift in a contract which requires interventions will '
        'show the user a warning if he closes it without creating any '
        'intervention.')
    working_shift_rules = fields.One2Many(
        'working_shift.contract.working_shift_rule',
        'contract', 'Working Shift Rules', states={
            'invisible': Eval('invoicing_method') != 'working_shift',
            })
    intervention_rules = fields.One2Many(
        'working_shift.contract.intervention_rule',
        'contract', 'Intervention Rules', states={
            'invisible': Eval('invoicing_method') != 'intervention',
            })
    intervention_fields = fields.One2Many('working_shift.contract.field',
        'contract', 'Intervention Fields')

    @staticmethod
    def default_invoicing_method():
        return 'working_shift'

    @fields.depends('invoicing_method')
    def on_change_invoicing_method(self):
        if self.invoicing_method == 'intervention':
            return {
                'requires_interventions': True,
                }
        return {}

    def compute_matching_working_shift_rule(self, working_shift, pattern=None):
        if pattern is None:
            pattern = {}
        else:
            pattern = pattern.copy()
        pattern['hours'] = working_shift.hours
        for rule in self.working_shift_rules:
            if rule.match(pattern):
                return rule

    def compute_matching_intervention_rule(self, intervention, pattern=None):
        if pattern is None:
            pattern = {}
        for rule in self.intervention_rules:
            if rule.match(pattern):
                return rule


class RuleMixin(ModelSQL, ModelView, MatchMixin):
    name = fields.Char('Name', required=True)
    contract = fields.Many2One('working_shift.contract', 'Contract',
        required=True, select=True, ondelete='CASCADE')
    sequence = fields.Integer('Sequence')
    # Result
    product = fields.Many2One('product.product', 'Product', required=True,
        domain=[
            ('template.default_uom.category', '=',
                Id('product', 'uom_cat_unit')),
            ])
    list_price = fields.Numeric('List Price', digits=(16, DIGITS),
        required=True, help="Price per hour to use when invoice to customers.")

    @classmethod
    def __setup__(cls):
        super(RuleMixin, cls).__setup__()
        cls._order = [
            ('contract', 'ASC'),
            ('sequence', 'ASC'),
            ]

    @staticmethod
    def order_sequence(tables):
        table, _ = tables[None]
        return [table.sequence == None, table.sequence]

    @fields.depends('product')
    def on_change_product(self):
        if self.product:
            return {
                'list_price': self.product.list_price,
                }
        return {}


class WorkingShiftRule(RuleMixin):
    'Contract Working Shift Rule'
    __name__ = 'working_shift.contract.working_shift_rule'
    # Matching
    hours = fields.Float('Hours', domain=[
            ['OR',
                ('hours', '=', None),
                ('hours', '>', 0),
                ],
            ])

    def match(self, pattern):
        if 'hours' in pattern and self.hours:
            pattern = pattern.copy()
            if self.hours < pattern.pop('hours'):
                return False
        return super(WorkingShiftRule, self).match(pattern)


class InterventionRule(RuleMixin):
    'Working Shift Contract Intervention Rule'
    __name__ = 'working_shift.contract.intervention_rule'


class Field:
    __name__ = 'ir.model.field'
    model_model = fields.Function(fields.Char('Model Name'),
        'on_change_with_model_model')
    working_shift_contract_managed = fields.Boolean('Contract Managed',
        states={
            'invisible': Eval('model_model') != 'working_shift.intervention',
            }, depends=['model_model'],
        help='If checked, this field will be available in the list of fields '
        'to be configured per Working Shift Contracts.')

    @fields.depends('model')
    def on_change_with_model_model(self, name=None):
        if self.model:
            return self.model.model


class ContractField(ModelSQL, ModelView):
    'Working Shift Contract Field'
    __name__ = 'working_shift.contract.field'
    contract = fields.Many2One('working_shift.contract', 'Contract',
        required=True, select=True, ondelete='CASCADE')
    field = fields.Many2One('ir.model.field', 'Field', required=True,
        domain=[
            ('model.model', '=', 'working_shift.intervention'),
            ('working_shift_contract_managed', '=', True),
            ])
    required = fields.Boolean('Required')

    @classmethod
    def __setup__(cls):
        super(ContractField, cls).__setup__()
        cls._sql_constraints += [
            ('contract_field_uniq', 'UNIQUE (contract, field)',
                'The Contract + Field tuple of the Working Shift Contract '
                'Field must be unique.'),
            ]
