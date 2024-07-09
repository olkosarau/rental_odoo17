from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import format_date
from math import ceil
from pytz import timezone, UTC
from odoo.tools import format_datetime, format_time


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

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

