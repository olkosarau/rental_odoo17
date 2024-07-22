from odoo import api, fields, models, tools


class RentalScheduleInherit(models.Model):
    _inherit = "sale.rental.schedule"
    _description = "Rental Schedule inherit"

    def _select(self):
        return """%s,
            %s,
            sol.product_id as product_id,
            t.uom_id as product_uom,
            sol.name as description,
            CASE WHEN s.days_calculation_type = 'one' THEN s.rental_start_date ELSE sol.start_date END AS pickup_date,
            CASE WHEN s.days_calculation_type = 'one' THEN s.rental_return_date ELSE sol.return_date END AS return_date,
            s.name as name,
            %s,
            s.date_order as order_date,
            s.state as state,
            s.rental_status as rental_status,
            s.partner_id as partner_id,
            s.user_id as user_id,
            s.company_id as company_id,
            extract(epoch from avg(date_trunc('day',s.rental_return_date)-date_trunc('day',s.rental_start_date)))/(24*60*60)::decimal(16,2) as delay,
            t.categ_id as categ_id,
            s.pricelist_id as pricelist_id,
            s.analytic_account_id as analytic_account_id,
            s.team_id as team_id,
            p.product_tmpl_id,
            partner.country_id as country_id,
            partner.commercial_partner_id as commercial_partner_id,
            CONCAT(partner.name, ', ', s.name) as card_name,
            s.id as order_id,
            sol.id as order_line_id,
            lot_info.lot_id as lot_id,
            s.warehouse_id as warehouse_id,
            %s,
            %s,
            %s
        """ % (self._id(), self._get_product_name(), self._quantity(), self._report_line_status(), self._late(), self._color())
