from odoo import api, fields, models


class DaysCalculationWarningWizard(models.TransientModel):
    _name = 'days.calculation.warning.wizard'

    days_calculation_type = fields.Selection([
        ('one', 'By Order Total'),
        ('multi', 'By Order lines')
    ], string='Days Calculation Type', required=True)

    def confirm_changes(self):
        self.ensure_one()
        sale_orders = self.env.context.get('active_ids') or []
        sale_order = self.env['sale.order'].browse(sale_orders[0])
        sale_order.write({'days_calculation_type': self.days_calculation_type})
        return {'type': 'ir.actions.act_close'}

    def cancel_changes(self):
        self.ensure_one()
        sale_orders = self.env.context.get('active_ids') or []
        sale_order = self.env['sale.order'].browse(sale_orders[0])
        sale_order.write({'days_calculation_type': sale_order.days_calculation_type})
        return {'type': 'ir.actions.act_close'}