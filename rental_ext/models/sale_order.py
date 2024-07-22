from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from math import ceil


class SaleOrder(models.Model):
    _inherit = "sale.order"


    days_calculation_type = fields.Selection(
        [('one', 'By Order Total'), ('multi', 'By Order lines')],
        string='Days Calculation', required=True, default='one', copy=False, index=True)
    check_time_update = fields.Boolean(string='Check Time Update', default=False, store=True, copy=False, compute='_compute_check_time_update')


    @api.onchange('days_calculation_type')
    def _onchange_days_calculation_type_custom(self):
        for line in self.order_line:
            if line.product_id.rent_ok:
                if self.days_calculation_type == 'multi':
                    duration = 0
                    if not line.start_date or not line.return_date:
                        line.update({
                            'start_date': line.start_date or fields.Datetime.now(),
                            'return_date': line.return_date or fields.Datetime.now() + relativedelta(days=1),
                        })
                    if line.start_date and line.return_date:
                        duration = line.return_date - line.start_date
                    line.update({
                        'is_order_multi': True,
                        'number_of_days': duration.days,
                        'remaining_hours': ceil(duration.seconds / 3600)
                    })
                else:
                    line.update({
                        'is_order_multi': False,
                    })
        self._onchange_duration_show_update_duration()


    @api.depends('order_line.start_date', 'order_line.return_date')
    def _compute_check_time_update(self):
        for order in self:
            order.check_time_update = any(line.is_rental for line in self.order_line)
            order.update({
                'show_update_duration': order.check_time_update,
            })

    def _update_order_line_info(self, product_id, quantity, **kwargs):
        if self.days_calculation_type == 'multi':
            for line in self.order_line:
                if line.product_id.id == product_id and line.is_order_multi:
                    return super()._update_order_line_info(
                        product_id,
                        quantity,
                        start_date=line.start_date,
                        end_date=line.return_date,
                        **kwargs,
                    )
        else:
            return super()._update_order_line_info(
                product_id,
                quantity,
                start_date=self.rental_start_date,
                end_date=self.rental_return_date,
                **kwargs,
            )


    def action_update_rental_prices(self):
        for order in self:
            if order.days_calculation_type == 'multi':
                for line in order.order_line:
                    line.update({
                        'start_date': line.start_date or fields.Datetime.now(),
                        'return_date': line.return_date or fields.Datetime.now() + relativedelta(days=1),
                    })
        return super().action_update_rental_prices()


    def _get_product_catalog_order_data(self, products, **kwargs):
        if self.days_calculation_type == 'multi':
            for line in self.order_line:
                if line.is_order_multi:
                    return super()._get_product_catalog_order_data(
                        products,
                        start_date=line.start_date,
                        end_date=line.return_date,
                        **kwargs,
                    )
        else:
            return super()._get_product_catalog_order_data(
                products,
                start_date=self.rental_start_date,
                end_date=self.rental_return_date,
                **kwargs,
            )
    #
    def action_confirm(self):
        # Additional logic when days_calculation_type is 'multi'
        for order in self:
            if order.days_calculation_type == 'multi':
                for line in order.order_line.filtered(lambda l: l.is_rental):
                    if not line.start_date:
                        raise ValidationError(_("Start date is required for rental lines."))
                    if not line.return_date:
                        raise ValidationError(_("Return date is required for rental lines."))
            if order.is_rental_order:
                order.action_update_rental_prices()
        super().action_confirm()
        return True
    #
    def _get_action_add_from_catalog_extra_context(self):
        extra_context = super()._get_action_add_from_catalog_extra_context()
        if self.days_calculation_type == 'multi':
            for line in self.order_line:
                if line.is_order_multi:
                    extra_context.update(start_date=line.start_date, end_date=line.return_date)
        else:
            extra_context.update(start_date=self.rental_start_date, end_date=self.rental_return_date)
        return extra_context


    @api.depends(
        'rental_start_date',
        'rental_return_date',
        'state',
        'order_line.is_rental',
        'order_line.product_uom_qty',
        'order_line.qty_delivered',
        'order_line.qty_returned',
        'days_calculation_type',
        'order_line.start_date',
        'order_line.return_date',
    )
    def _compute_rental_status(self):
        self.next_action_date = False
        for order in self:
            if order.days_calculation_type == 'multi':
                if order.state in ['sale', 'done'] and order.is_rental_order:
                    rental_order_lines = order.order_line.filtered(
                        lambda l: l.is_rental and l.start_date and l.return_date)
                    pickeable_lines = rental_order_lines.filtered(
                        lambda sol: sol.qty_delivered < sol.product_uom_qty)
                    returnable_lines = rental_order_lines.filtered(lambda sol: sol.qty_returned < sol.qty_delivered)
                    min_pickup_date = min(pickeable_lines.mapped('start_date')) if pickeable_lines else 0
                    min_return_date = min(returnable_lines.mapped('return_date')) if returnable_lines else 0
                    if min_pickup_date and pickeable_lines and (
                            not returnable_lines or min_pickup_date <= min_return_date):
                        order.rental_status = 'pickup'
                        order.next_action_date = min_pickup_date
                    elif returnable_lines:
                        order.rental_status = 'return'
                        order.next_action_date = min_return_date
                    else:
                        order.rental_status = 'returned'
                        order.next_action_date = False
                    order.has_pickable_lines = bool(pickeable_lines)
                    order.has_returnable_lines = bool(returnable_lines)
                else:
                    order.has_pickable_lines = False
                    order.has_returnable_lines = False
                    order.rental_status = order.state if order.is_rental_order else False
                    order.next_action_date = False
            else:
                if not order.is_rental_order:
                    order.rental_status = False
                elif order.state != 'sale':
                    order.rental_status = order.state
                elif order.has_pickable_lines:
                    order.rental_status = 'pickup'
                    order.next_action_date = order.rental_start_date
                elif order.has_returnable_lines:
                    order.rental_status = 'return'
                    order.next_action_date = order.rental_return_date
                else:
                    order.rental_status = 'returned'



    def _rental_set_all_dates(self, order_line):
        self.ensure_one()
        if order_line.start_date and order_line.start_date:
            self.sudo().write({
                'rental_start_date': order_line.start_date,
                'rental_return_date': order_line.return_date,
            })
            return

        start_date = fields.Datetime.now().replace(minute=0, second=0) + relativedelta(hours=1)
        return_date = start_date + relativedelta(days=1)
        self.update({
            'rental_start_date': start_date,
            'rental_return_date': return_date,
        })
