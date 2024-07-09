from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import format_date
from math import ceil
from pytz import timezone, UTC
from odoo.tools import format_datetime, format_time


class SaleOrder(models.Model):
    _inherit = "sale.order"

    days_calculation_type = fields.Selection(
        [('one', 'By Order Total'), ('multi', 'By Order lines')],
        string='Days Calculation', required=True, default='one')

    def _rental_set_dates(self):
        self.ensure_one()
        if self.days_calculation_type == 'one':
            if self.rental_start_date and self.rental_return_date:
                return
            start_date = fields.Datetime.now().replace(minute=0, second=0) + relativedelta(hours=1)
            return_date = start_date + relativedelta(days=1)
            self.update({
                'rental_start_date': start_date,
                'rental_return_date': return_date,
            })
        # else:
        #     self.rental_start_date = False
        #     self.rental_return_date = False

    # === ONCHANGE METHODS ===#

    @api.onchange('rental_start_date', 'rental_return_date')
    def _onchange_duration_show_update_duration(self):
        if self.days_calculation_type == 'one':
            self.show_update_duration = any(line.is_rental for line in self.order_line)

    @api.onchange('is_rental_order')
    def _onchange_is_rental_order(self):
        self.ensure_one()
        if self.days_calculation_type == 'one':
            if self.is_rental_order:
                self._rental_set_dates()

    @api.onchange('days_calculation_type')
    def _onchange_days_calculation_type(self):
        if self.days_calculation_type == 'multi':
            self.rental_start_date = False
            self.rental_return_date = False
            for line in self.order_line:
                if line.is_rental:
                    line.start_date = fields.Datetime.now().replace(minute=0, second=0) + relativedelta(hours=1)
                    line.return_date = line.start_date + relativedelta(days=1)
        else:
            self._rental_set_dates()

    @api.depends('order_line.is_rental')
    def _compute_has_rented_products(self):
        for so in self:
            so.has_rented_products = any(line.is_rental for line in so.order_line)

    def _get_product_catalog_order_data(self, products, **kwargs):
        if self.days_calculation_type == 'one':
            return super()._get_product_catalog_order_data(
                products,
                start_date=self.rental_start_date,
                end_date=self.rental_return_date,
                **kwargs,
            )

    def _get_action_add_from_catalog_extra_context(self):
        extra_context = super()._get_action_add_from_catalog_extra_context()
        if self.days_calculation_type == 'one':
            extra_context.update(start_date=self.rental_start_date, end_date=self.rental_return_date)
        return extra_context

    def _update_order_line_info(self, product_id, quantity, **kwargs):
        if self.days_calculation_type == 'one':
            if self.is_rental_order:
                self = self.with_context(in_rental_app=True)
                product = self.env['product.product'].browse(product_id)
                if product.is_product_rentable:
                    self._rental_set_dates()
            return super()._update_order_line_info(
                product_id,
                quantity,
                start_date=self.rental_start_date,
                end_date=self.rental_return_date,
                **kwargs,
            )
        else:
            for line in self.order_line:
                if line.product_id.id == product_id:
                    return super()._update_order_line_info(
                        product_id,
                        quantity,
                        start_date=line.start_date,
                        end_date=line.return_date,
                        **kwargs,
                    )

    @api.depends(
        'rental_start_date',
        'rental_return_date',
        'state',
        'order_line.is_rental',
        'order_line.product_uom_qty',
        'order_line.qty_delivered',
        'order_line.qty_returned',
        "days_calculation_type",
        'order_line.start_date',
        'order_line.return_date',
    )
    def _compute_rental_status(self):
        self.next_action_date = False
        for order in self:
            if order.days_calculation_type == 'one':
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
            else:
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

    @api.onchange('rental_start_date', 'rental_return_date')
    def _onchange_duration_show_update_duration(self):
        for order in self:
            if order.days_calculation_type == 'one':
                order.show_update_duration = any(line.is_rental for line in order.order_line)

    def _prepare_sale_order_write(self, vals):
        if 'days_calculation_type' in vals and vals.get('days_calculation_type') == 'multi':
            vals['rental_start_date'] = False
            vals['rental_return_date'] = False
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._prepare_sale_order_write(vals) for vals in vals_list]

        return super(SaleOrder, self).create(vals_list)

    def write(self, values):
        for order in self:
            if order.days_calculation_type == 'multi' and values.get('rental_return_date'):
                del values['rental_return_date']
            if order.days_calculation_type == 'multi' and values.get('rental_start_date'):
                del values['rental_start_date']
        result = super().write(values)
        values = self._prepare_sale_order_write(values)
        return result


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    start_date = fields.Datetime(string="Start day", store=True, readonly=False)
    return_date = fields.Datetime(string="Return", store=True, readonly=False)

    days_calculation_type = fields.Selection(related='order_id.days_calculation_type')
    is_order_multi = fields.Boolean(
        string="Is multi", compute='_compute_is_order_multi', default=False
    )
    number_of_days = fields.Integer(
        compute="_compute_number_of_days",
        readonly=False,
        store=True,
        string="Number of Days",
    )
    is_late = fields.Boolean(
        string="Is overdue", compute='_compute_is_late',
        help="The products haven't been returned in time")
    remaining_hours = fields.Integer(
        string="Remaining duration in hours",
        compute='_compute_number_of_days',
        store=True
    )

    @api.onchange('start_date')
    def _onchange_start_date(self):
        if self.days_calculation_type == 'multi':
            self.order_id._recompute_rental_prices()

    @api.onchange('return_date')
    def _onchange_return_date(self):
        if self.days_calculation_type == 'multi':
            self.order_id._recompute_rental_prices()


    def action_update_rental_prices_lines(self):
        self.order_id.action_update_rental_prices()

    @api.depends('days_calculation_type')
    def _compute_is_order_multi(self):
        for line in self:
            line.is_order_multi = line.order_id.days_calculation_type == 'multi'

    @api.depends('return_date')
    def _compute_is_late(self):
        now = fields.Datetime.now()
        for line in self:
            line.is_late = line.return_date and line.return_date + timedelta(hours=line.company_id.min_extra_hour) < now

    @api.depends('order_id.rental_start_date', 'start_date')
    def _compute_reservation_begin(self):
        lines = self.filtered(lambda line: line.is_rental)
        for line in lines:
            if line.days_calculation_type == 'one':
                line.reservation_begin = line.order_id.rental_start_date
                (self - lines).reservation_begin = None
            else:
                line.reservation_begin = line.start_date or fields.Datetime.now()
                (self - lines).reservation_begin = None

    @api.depends("start_date", "return_date")
    def _compute_number_of_days(self):
        for line in self:
            if line.days_calculation_type == 'multi':
                start_date = line.start_date
                return_date = line.return_date

                if start_date and return_date:
                    duration = return_date - start_date
                    line.number_of_days = duration.days
                    line.remaining_hours = ceil(duration.seconds / 3600)
                else:
                    line.number_of_days = False
                    line.remaining_hours = False
            else:
                line.number_of_days = False
                line.remaining_hours = False

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.is_product_rentable and self.is_rental:
            self.update({
                'is_rental': True,
                'start_date': fields.Datetime.now(),
                'return_date': fields.Datetime.now() + relativedelta(days=1),
            })

    @api.depends('product_id', 'product_uom_qty', 'price_unit', 'start_date', 'return_date')
    def _compute_name(self):
        for line in self:
            name = line.product_id.display_name or ''
            if line.is_rental and line.start_date and line.return_date:
                name += '\n{} to {}'.format(
                    format_datetime(self.env, line.start_date),
                    format_datetime(self.env, line.return_date)
                )
            line.name = name

    _sql_constraints = [
        ('rental_stock_coherence',
         "CHECK(NOT is_rental OR qty_returned <= qty_delivered)",
         "You cannot return more than what has been picked up."),
        ('rental_period_coherence',
         "CHECK(NOT is_rental OR start_date < return_date)",
         "Please choose a return date that is after the pickup date."),
    ]

    @api.constrains("product_id", "start_date", "return_date")
    def _check_start_end_dates(self):
        for line in self:
            if line.product_id.rent_ok:
                if not line.return_date:
                    raise ValidationError(
                        _("Missing End Date for sale order line with Product '%s'.")
                        % (line.product_id.display_name)
                    )
                if not line.start_date:
                    raise ValidationError(
                        _("Missing Start Date for sale order line with Product '%s'.")
                        % (line.product_id.display_name)
                    )
                if line.start_date > line.return_date:
                    raise ValidationError(
                        _("Start date (%(start_date)s) should be before or "
                          "be the same as end date (%(return_date)s) for "
                          "sale order line with product '%(product_name)s'.",
                          start_date=format_date(self.env, line.start_date),
                          return_date=format_date(self.env, line.return_date),
                          product_name=line.product_id.display_name,
                        )
                    )

    def _get_rental_order_line_description(self):
        tz = self._get_tz()
        start_date = False
        return_date = False
        if self.order_id.days_calculation_type == 'one':
            start_date = self.order_id.rental_start_date
            return_date = self.order_id.rental_return_date
        else:
            start_date = self.start_date
            return_date = self.return_date
        env = self.with_context(use_babel=True).env
        if start_date and return_date \
           and start_date.replace(tzinfo=UTC).astimezone(timezone(tz)).date() \
               == return_date.replace(tzinfo=UTC).astimezone(timezone(tz)).date():
            return_date_part = format_time(env, return_date, tz=tz, time_format=False)
        else:
            return_date_part = format_datetime(env, return_date, tz=tz, dt_format=False)
        start_date_part = format_datetime(env, start_date, tz=tz, dt_format=False)
        return _(
            "\n%(from_date)s to %(to_date)s", from_date=start_date_part, to_date=return_date_part
        )

    def _prepare_procurement_values(self, group_id=False):
        """ Change the planned and deadline dates of rental delivery pickings. """
        values = super()._prepare_procurement_values(group_id)
        if self.order_id.days_calculation_type == 'one':
            if self.is_rental and self.env.user.has_group('sale_stock_renting.group_rental_stock_picking'):
                values.update({
                    'date_planned': self.order_id.rental_start_date,
                    'date_deadline': self.order_id.rental_start_date,
                })
            return values

