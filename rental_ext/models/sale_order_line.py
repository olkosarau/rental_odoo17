from dateutil.relativedelta import relativedelta
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from math import ceil
from odoo.tools import format_datetime, format_time
from odoo.tools.misc import groupby as tools_groupby



class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"


    start_date = fields.Datetime(string="Start day", store=True, copy=False, index=True, related=False)
    return_date = fields.Datetime(string="Return", store=True, copy=False, index=True, related=False)
    #
    # days_calculation_type = fields.Selection(related='order_id.days_calculation_type')
    is_order_multi = fields.Boolean(string="Is multi",  default=False, store=True, copy=False)

    number_of_days = fields.Integer(
        compute="_compute_number_of_days",
        readonly=False,
        store=True,
        string="Number of Days",
        copy=False,
    )
    # is_late = fields.Boolean(
    #     string="Is overdue", compute='_compute_is_late',
    #     help="The products haven't been returned in time")
    remaining_hours = fields.Integer(
        string="Remaining duration in hours",
        compute='_compute_number_of_days',
        store=True
    )

    @api.depends('order_id.rental_start_date', 'start_date', 'return_date')
    def _compute_reservation_begin(self):
        lines = self.filtered('is_rental')
        for line in lines:
            if line.order_id.days_calculation_type == 'multi':
                line.reservation_begin = line.start_date
            else:
                line.reservation_begin = line.order_id.rental_start_date
        (self - lines).reservation_begin = None


    @api.depends("start_date", "return_date")
    def _compute_number_of_days(self):
        for line in self:
            line.sudo().update({
                'number_of_days': False,
                'remaining_hours': False,
            })
            if line.order_id.days_calculation_type == 'multi':
                if line.start_date and line.return_date:
                    duration = line.return_date - line.start_date
                    line.update({
                        # 'start_date': line.start_date or fields.Datetime.now(),
                        # 'return_date': line.return_date or fields.Datetime.now() + relativedelta(days=1),
                        'number_of_days': duration.days,
                        'remaining_hours': ceil(duration.seconds / 3600),
                        'is_order_multi': True,
                    })

    @api.onchange('product_id')
    def _onchange_multi_rent_product_id(self):
        if self.is_product_rentable and self.is_rental:
            self.update({
                'start_date': fields.Datetime.now(),
                'return_date': fields.Datetime.now() + relativedelta(days=1),
            })

    @api.depends('product_id', 'product_uom_qty', 'price_unit', 'start_date', 'return_date')
    def _compute_name(self):
        for line in self:
            name = line.product_id.display_name or ''
            if line.is_order_multi:
                if line.is_rental and line.start_date and line.return_date:
                    name += '\n{} to {}'.format(
                        format_datetime(self.env, line.start_date),
                        format_datetime(self.env, line.return_date)
                    )
            elif line.is_rental and line.order_id:
                name += '\n{} to {}'.format(
                    format_datetime(self.env, line.order_id.rental_start_date or fields.Datetime.now()),
                    format_datetime(self.env, line.order_id.rental_return_date)
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

    def create(self, vals_list):
        record = super().create(vals_list)
        for line in record:
            if line.is_rental and line.order_id.days_calculation_type == 'multi':
                line.update({
                    'is_order_multi': True,
                })
        return record

    def write(self, values):
        record = super().write(values)
        for line in self:
            if line.is_rental and line.start_date and line.return_date:
                if line.start_date > line.return_date:
                    raise ValidationError(
                        _("Start date (%(start_date)s) should be before or "
                          "be the same as end date (%(return_date)s) for "
                          "sale order line with product '%(product_name)s'.",
                          start_date=format(line.start_date),
                          return_date=format(line.return_date),
                          product_name=line.name)
                    )
        return record

    def _prepare_procurement_values(self, group_id=False):
        """ Change the planned and deadline dates of rental delivery pickings. """
        values = super()._prepare_procurement_values(group_id)

        if self.is_rental and self.env.user.has_group('sale_stock_renting.group_rental_stock_picking'):
            if self.order_id.days_calculation_type == 'multi':
                values.update({
                    'date_planned': self.start_date if self.start_date else self.start_date,
                    'date_deadline': self.return_date if self.return_date else self.return_date,
                })
            else:
                values.update({
                    'date_planned': self.order_id.rental_start_date,
                    'date_deadline': self.order_id.rental_start_date,
                })
        return values

    def _get_pricelist_price(self):
        """ Custom price computation for rental lines.

        The displayed price will only be the price given by the product.pricing rules matching the
        given line information (product, period, pricelist, ...).
        """
        self.ensure_one()
        if self.is_rental:
            if self.order_id.days_calculation_type == 'multi':
                self.order_id._rental_set_all_dates(self)
                return self.order_id.pricelist_id._get_product_price(
                    self.product_id.with_context(**self._get_product_price_context()),
                    self.product_uom_qty or 1.0,
                    currency=self.currency_id,
                    uom=self.product_uom,
                    date=self.order_id.date_order or fields.Date.today(),
                    start_date=self.start_date,
                    end_date=self.return_date,
                )
            else:
                self.order_id._rental_set_dates()
                return self.order_id.pricelist_id._get_product_price(
                    self.product_id.with_context(**self._get_product_price_context()),
                    self.product_uom_qty or 1.0,
                    currency=self.currency_id,
                    uom=self.product_uom,
                    date=self.order_id.date_order or fields.Date.today(),
                    start_date=self.start_date,
                    end_date=self.return_date,
                )
        return super()._get_pricelist_price()



