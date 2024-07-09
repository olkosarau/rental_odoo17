{
    "name": "Renting Sale Start End Dates",
    "version": "17.0.1.0.0",
    "category": "Sales",
    "summary": "Adds start date and end date on renting sale order lines",
    "depends": [
        "base",
        "sale_renting",
    ],
    "data": [
        'security/ir.model.access.csv',
        "views/sale_order.xml",
        "wizard/days_calculation_warning_wizard_views.xml",
    ],
    "installable": True,
}
