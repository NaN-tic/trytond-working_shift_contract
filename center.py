# The COPYRIGHT file at the top level of this repository contains the full

from trytond.model import ModelSQL, ModelView, fields

__all__ = ['Center']


class Center(ModelSQL, ModelView):
    'Center'
    __name__ = 'working_shift.center'

    name = fields.Char('Name', required=True)
    color = fields.Selection([
        ('soft_blue', 'Soft Blue'),
        ('green', 'Green'),
        ('orange', 'Orange'),
        ('white', 'White'),
        ('red', 'Red'),
        ('yellow', 'Yellow'),
        ('navy_blue', 'Navy Blue')
        ], 'Color', required=True)
